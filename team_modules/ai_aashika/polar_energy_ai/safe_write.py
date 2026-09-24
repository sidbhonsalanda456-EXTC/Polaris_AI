import json as _json
import os as _os
import time as _time


def _retry(action, path, context, attempts=4, delay=1.0):
    for i in range(attempts):
        try:
            action()
            return True
        except PermissionError:
            if i == attempts - 1:
                print(f"  [!] {context} is locked by another program (open in Excel?):")
                print(f"      {path}")
                print(f"      -> this write was skipped so the run continues; "
                      f"close the file and press Run again to include it.")
                return False
            _time.sleep(delay)
    return False


def write_csv(df, path, **kwargs):
    kwargs.setdefault("index", False)
    return _retry(lambda: df.to_csv(path, **kwargs), path, "DATA FILE")


def save_workbook(workbook, path):
    return _retry(lambda: workbook.save(path), path, "EXCEL FILE")


def write_json(obj, path):
    def _do():
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            _json.dump(obj, fh, indent=2)
        _os.replace(tmp, path)

    return _retry(_do, path, "JSON FILE")


def write_text(text, path):
    def _do():
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        _os.replace(tmp, path)

    return _retry(_do, path, "TEXT FILE")