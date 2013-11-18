# -*- coding: utf-8 -*-
from collections import namedtuple
import functools
import fnmatch
from itertools import groupby
from os import path, walk
import re, io
import threading
import sublime
import sublime_plugin

Message = namedtuple('Message', 'type, msg')

def do_when(conditional, callback, *args, **kwargs):
    if conditional():
        return callback(*args, **kwargs)
    sublime.set_timeout(functools.partial(
        do_when, conditional, callback, *args, **kwargs), 50)


class PlainTasksThreadProgress(object):
    def __init__(self, thread, message, success_message, file_counter):
        self.thread = thread
        self.message = message
        self.success_message = success_message
        self.file_counter = file_counter
        self.addend = 1
        self.size = 8
        sublime.set_timeout(lambda: self.run(0), 100)

    def run(self, i):
        if not self.thread.is_alive():
            if hasattr(self.thread, 'result') and not self.thread.result:
                sublime.status_message('')
                return
            sublime.status_message(self.success_message)
            return
        before = i % self.size
        after = (self.size - 1) - before
        sublime.status_message('%s [%s=%s] (%s files scanned)' % (self.message, ' ' * before, ' ' * after, self.file_counter))
        if not after:
            self.addend = -1
        if not before:
            self.addend = 1
        i += self.addend
        sublime.set_timeout(lambda: self.run(i), 100)


class PlainTasksTodoExtractor(object):
    def __init__(self, settings, filepaths, dirpaths, ignored_dirs, ignored_file_patterns, file_counter, case_sensitive):
        self.filepaths = filepaths
        self.dirpaths = dirpaths
        self.patterns = settings.get('patterns')
        self.settings = settings
        self.file_counter = file_counter
        self.ignored_dirs = ignored_dirs
        self.ignored_files = ignored_file_patterns
        self.case_sensitive = case_sensitive

    def iter_files(self):
        seen_paths_ = []
        files = self.filepaths
        dirs = self.dirpaths
        exclude_dirs = self.ignored_dirs
        for filepath in files:
            pth = path.realpath(path.abspath(filepath))
            if pth not in seen_paths_:
                seen_paths_.append(pth)
                yield pth
        for dirpath in dirs:
            dirpath = path.abspath(dirpath)
            for dirpath, dirnames, filenames in walk(dirpath):
                for dir in exclude_dirs:
                    if dir in dirnames:
                        dirnames.remove(dir)
                for filepath in filenames:
                    pth = path.join(dirpath, filepath)
                    pth = path.realpath(path.abspath(pth))
                    if pth not in seen_paths_:
                        seen_paths_.append(pth)
                        yield pth

    def filter_files(self, files):
        exclude_patterns = [re.compile(patt) for patt in self.ignored_files]
        for filepath in files:
            if any(patt.search(filepath) for patt in exclude_patterns):
                continue
            yield filepath

    def search_targets(self):
        """Yield filtered filepaths for message extraction"""
        return self.filter_files(self.iter_files())

    def extract(self):
        message_patterns = '|'.join(self.patterns.values())
        case_sensitivity = 0 if self.case_sensitive else re.IGNORECASE
        patt = re.compile(message_patterns, case_sensitivity)
        for filepath in self.search_targets():
            try:
                f = io.open(filepath, 'r', encoding='utf-8')
                for linenum, line in enumerate(f):
                    for mo in patt.finditer(line):
                        matches = [Message(msg_type, msg) for msg_type, msg in mo.groupdict().items() if msg]
                        for match in matches:
                            yield {'filepath': filepath, 'linenum': linenum + 1, 'match': match}
            except (IOError, UnicodeDecodeError):
                f = None # broken symlink, probably
            finally:
                self.file_counter.increment()
                if f is not None:
                    f.close()


class PlainTasksRenderResultRunCommand(sublime_plugin.TextCommand):
    def run(self, edit, formatted_results, file_counter):
        eol = self.view.sel()[0].a
        for line in formatted_results:
            eol += self.view.insert(edit, eol, line + '\n')


class PlainTasksWorkerThread(threading.Thread):
    def __init__(self, extractor, callback, file_counter):
        self.extractor = extractor
        self.callback = callback
        self.file_counter = file_counter
        threading.Thread.__init__(self)

    def run(self):
        ## Extract in this thread
        todos = self.extractor.extract()
        formatted = list(self.format(todos))
        sublime.set_timeout(functools.partial(self.callback, formatted, self.file_counter), 10)

    def format(self, messages):
        key_func = lambda m: m['match'].type
        messages = sorted(messages, key=key_func)
        for message_type, matches in groupby(messages, key=key_func):
            matches = list(matches)
            if matches:
                yield (u'\n{0} ({1})'.format(message_type.upper(), len(matches)))
                for m in matches:
                    msg = m['match'].msg
                    filepath = path.basename(m['filepath'])
                    line = u"  ☐ .\{filepath}:{linenum}\"{msg}\"".format(filepath=filepath, linenum=m['linenum'], msg=msg)
                    yield (line)


class PlainTasksFileScanCounter(object):
    """Thread-safe counter used to update the status bar"""
    def __init__(self):
        self.ct = 0
        self.lock = threading.RLock()

    def __call__(self, filepath):
        self.log.debug(u'Scanning %s' % filepath)
        self.increment()

    def __str__(self):
        with self.lock: return '%d' % self.ct

    def increment(self):
        with self.lock: self.ct += 1

    def reset(self):
        with self.lock: self.ct = 0


class PlainTasksExtractTodoCommand(sublime_plugin.TextCommand):
    def search_paths(self, window, open_files_only=False):
        """Return (filepaths, dirpaths)"""
        return ([view.file_name() for view in window.views() if view.file_name()],
                window.folders() if not open_files_only else [])

    def run(self, edit, open_files_only=False):
        filepaths, dirpaths = self.search_paths(self.view.window(), open_files_only=open_files_only)

        settings = sublime.load_settings('PlainTasksExtractTodo.sublime-settings')
        ignored_dirs = settings.get('folder_exclude_patterns', [])
        global_settings = sublime.load_settings('Preferences.sublime-settings')
        ignored_dirs.extend(global_settings.get('folder_exclude_patterns', []))
        exclude_file_patterns = settings.get('file_exclude_patterns', [])
        exclude_file_patterns.extend(global_settings.get('file_exclude_patterns', []))
        exclude_file_patterns.extend(global_settings.get('binary_file_patterns', []))
        exclude_file_patterns = [fnmatch.translate(patt) for patt in exclude_file_patterns]
        case_sensitive = settings.get('case_sensitive', False)

        file_counter = PlainTasksFileScanCounter()
        extractor = PlainTasksTodoExtractor(settings, filepaths, dirpaths, ignored_dirs, exclude_file_patterns, file_counter, case_sensitive)
        worker_thread = PlainTasksWorkerThread(extractor, self.render_formatted, file_counter)
        worker_thread.start()
        PlainTasksThreadProgress(worker_thread, 'Finding TODOs', '', file_counter)

    def render_formatted(self, rendered, counter):
        self.view.run_command("plain_tasks_render_result_run", {"formatted_results": rendered, "file_counter": str(counter)})
