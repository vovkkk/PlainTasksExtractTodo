This is SublimeTODO fork aims to extract todo-style comments to PlainTasks format. This plugin is supposed to work with 2 and 3 versions of Sublime Text.

- __Config__  
    You may find default configuration in `Preferences > Package Settings`  
    Possible settings (abscent by default):  
    - `"case_sensitive": true`
    - `"folder_exclude_patterns": ["vendor", "tmp"]`
    - `"file_exclude_patterns": ["*.css"]`
    - `"binary_file_patterns: ["*.bin"]`
- __Usage__  
    Either via command palette or bind keystroke for `plain_tasks_extract_todo`.  
    _Note_ that extracted results will be placed in active tab after cursor.
- __Navigating results__  
    This plugin doesn't provide any keybinding, since links will be handled by PlainTasks.  
    Still, you can easily customize it, e.g. to open link by `enter` key:  

    ```
    {"keys": ["enter"], "command": "plain_tasks_open_link",
    "context": [{"key": "selector", "operator": "equal", "operand": "text.todo meta.item"}]}
    ```

# License
All of SublimeTODO is licensed under the MIT license.  
Copyright (c) 2012 Rob Cowie <szaz@mac.com>
