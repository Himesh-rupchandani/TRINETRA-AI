#!/usr/bin/env python3
"""Keep the server-side OpenCV install safe on headless machines.

Ultralytics declares ``opencv-python`` as a dependency, while this project
runs its backend and CV engine without an X11/GUI stack.  pip can therefore
leave both OpenCV distributions installed, with the GUI build winning the
``cv2`` import and failing with ``libGL.so.1``.

Run this script with the same Python interpreter used for the application,
after installing backend or cv-engine requirements.  It removes GUI OpenCV
only when present and installs the headless wheel only when needed.  Existing
headless installations are left alone, so normal application startup does
not redownload a large wheel.
"""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys

HEADLESS = "opencv-python-headless"
GUI_PACKAGES = ("opencv-python", "opencv-contrib-python")


def installed(name: str) -> bool:
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def pip(*args: str) -> None:
    command = [sys.executable, "-m", "pip", "--disable-pip-version-check", *args]
    subprocess.run(command, check=True)


def main() -> None:
    gui = [name for name in GUI_PACKAGES if installed(name)]
    has_headless = installed(HEADLESS)

    if not gui and has_headless:
        print("OpenCV is already configured for headless use.")
        return

    for name in gui:
        print(f"Removing GUI OpenCV package: {name}")
        pip("uninstall", "-y", name)

    # Reinstall when a GUI package was removed: both distributions own cv2
    # files, so a plain 'already satisfied' check is not enough to repair a
    # mixed installation.
    if gui or not has_headless:
        print("Installing the headless OpenCV package...")
        pip("install", "--force-reinstall", "--no-deps", f"{HEADLESS}>=4.9.0")

    print("Headless OpenCV is ready.")


if __name__ == "__main__":
    main()
