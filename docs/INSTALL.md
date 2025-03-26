# Installation Guide for Incrementum

This guide provides instructions on how to set up and run the Incrementum project primarily on an **Arch Linux-based system** (like CachyOS, EndeavourOS, Manjaro, Arch Linux). It uses `uv` for Python package management and `pacman` for system dependencies.

## Prerequisites

Before you begin, ensure you have the following installed on your system:

1.  **Arch-based Linux:** These instructions are tailored for distributions using `pacman`.
2.  **Git:** For cloning the repository.
    ```bash
    sudo pacman -Syu git
    ```
3.  **Python (Version 3.11 or 3.12 recommended):** This project relies on Python features and library compatibility from these versions. We'll use Python 3.11 in the examples.
    ```bash
    # Install Python 3.11 (or python312 if you prefer)
    sudo pacman -S python311
    ```
4.  **uv:** The fast Python package installer used for managing dependencies.
    ```bash
    sudo pacman -S uv
    ```
5.  **Qt6 System Libraries:** PyQt6 relies on the underlying Qt C++ libraries. Install the necessary components using `pacman`. `requirements.txt` **does not** handle these system libraries.
    ```bash
    # Install core Qt6 libs + modules needed by Incrementum (WebEngine, Charts, SVG)
    sudo pacman -S qt6-base qt6-declarative qt6-svg qt6-webengine qt6-charts
    ```
    *(Note: If you encounter `ModuleNotFoundError` later related to other Qt modules, you might need to install corresponding `qt6-<module>` packages here.)*

## Installation Steps

1.  **Clone the Repository:**
    Open your terminal and clone the Incrementum repository:
    ```bash
    git clone https://www.github.com/leisrich/incrementum.git
    cd incrementum # Navigate into the cloned directory
    ```

2.  **Create a Python Virtual Environment:**
    It's highly recommended to use a virtual environment to isolate project dependencies. Use `uv` with your chosen Python version (e.g., 3.11):
    ```bash
    # Create a virtual environment named .venv using python3.11
    uv venv -p python3.11
    ```
    *(This creates a `.venv` directory within your project folder.)*

3.  **Activate the Virtual Environment:**
    Activate the environment before installing packages:
    ```bash
    source .venv/bin/activate
    ```
    *(Your terminal prompt should now be prefixed with `(.venv)`)*

4.  **Install Python Dependencies:**
    Use `uv` to install all required Python packages listed in the `requirements.txt` file:
    ```bash
    uv pip install -r requirements.txt
    ```
    *(This will install PyQt6, PyQt6-WebEngine, PyQt6-Charts, NLTK, and other necessary Python libraries.)*

## Running the Application

Once the installation is complete:

1.  **Ensure the virtual environment is active:**
    If you open a new terminal, reactivate it:
    ```bash
    source .venv/bin/activate
    ```

2.  **Run the main script:**
    ```bash
    python main.py
    ```

3.  **First Run Note:** On the very first run, the application might download necessary data files for the NLTK library (used for natural language processing tasks). This is normal and should only happen once.

## Troubleshooting

* **`ModuleNotFoundError: No module named 'PyQt6.Qt...'`:** This usually means a required *system* Qt library is missing. Double-check the `pacman -S qt6-...` command in the Prerequisites section and ensure all necessary modules (like `qt6-webengine`, `qt6-charts`) are installed.
* **`uv: command not found` or `python3.11: command not found`:** Make sure you completed the Prerequisites section correctly.
* **Errors during `uv pip install`:** Ensure you have the `base-devel` package group installed (`sudo pacman -S --needed base-devel`) for compiling any potential dependencies, although `uv` often uses pre-built wheels when available. Ensure the virtual environment is active.

## Notes for Other Operating Systems

While this guide focuses on Arch Linux, the general steps for other systems are:
1.  Install Git, Python (3.11/3.12), and `uv` using your system's package manager (`apt`, `brew`, etc.).
2.  Install the **Qt6 development libraries** using your system's package manager (package names will differ significantly, e.g., `qt6-base-dev`, `libqt6websockets6-dev`, `qml6-module-qtwebengine`, `qml6-module-qtcharts` on Debian/Ubuntu based systems). This is often the trickiest part.
3.  Clone the repository.
4.  Create and activate a virtual environment (`uv venv -p python3.11`, `source .venv/bin/activate`).
5.  Install Python dependencies (`uv pip install -r requirements.txt`).
6.  Run the application (`python main.py`).

## Installation on Windows

These instructions guide you through installing Incrementum on Windows. Setting up development environments, especially those involving compiled libraries like Qt, can sometimes be more complex on Windows.

### Prerequisites (Windows)

1.  **Git:** Download and install [Git for Windows](https://git-scm.com/download/win). Allow it to add Git to your PATH during installation.
2.  **Python (Version 3.11 or 3.12 recommended):**
    * Download the installer from [python.org](https://www.python.org/downloads/windows/).
    * **Important:** During installation, check the box "Add Python x.x to PATH".
    * We'll assume Python 3.11 for these instructions.
3.  **`uv`:**
    * Open PowerShell (you can search for it in the Start Menu).
    * Run the following command to download and install `uv`:
        ```powershell
        irm [https://astral.sh/uv/install.ps1](https://astral.sh/uv/install.ps1) | iex
        ```
    * Alternatively, after installing Python, you can use pip: `pip install uv`.
4.  **Qt6 Development Libraries (via Official Installer):** This is the most crucial and potentially complex step. `requirements.txt` only installs the Python *bindings*; you need the actual Qt C++ libraries.
    * Download the **Qt Online Installer** from the [official Qt website](https://www.qt.io/download-qt-installer) (requires a free Qt Account).
    * Run the installer. When you reach the component selection screen:
        * Select a recent Qt 6 version (e.g., 6.7.x, 6.8.x).
        * Under that version, select the component matching your Python installation, typically **MSVC 2019 64-bit** (or a newer MSVC version if appropriate for your setup). **Do not** select MinGW unless you specifically built Python with it.
        * Ensure the following modules are checked under your chosen MSVC component: `Qt Base (Core, GUI, Widgets, etc.)`, `Qt SVG`, `Qt Declarative`, `Qt WebEngine`, `Qt Charts`.
        * Complete the installation.
    * **Add Qt to PATH:** You *must* add the `bin` directory of your installed Qt version to your system's PATH environment variable so Python and other tools can find the necessary DLLs.
        * Find the path, typically like `C:\Qt\<Your_Qt_Version>\msvc2019_64\bin` (e.g., `C:\Qt\6.7.0\msvc2019_64\bin`).
        * Search for "Environment Variables" in the Windows Start Menu, open "Edit the system environment variables".
        * Click "Environment Variables...".
        * Under "System variables" (or "User variables" if you prefer), find the `Path` variable, select it, and click "Edit...".
        * Click "New" and paste the path to the Qt `bin` directory.
        * Click OK on all dialogs. You may need to restart your terminal or even log out/in for the changes to take effect fully.
5.  **C++ Build Tools (Optional but recommended):** If `uv pip install` fails on some packages requiring compilation, you might need Microsoft C++ Build Tools. Install "Desktop development with C++" via the [Visual Studio Installer](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (select Build Tools).

### Installation Steps (Windows)

1.  **Clone the Repository:**
    Open Git Bash, Command Prompt, or PowerShell:
    ```bash
    git clone https://www.github.com/leisrich/incrementum.git
    cd incrementum
    ```

2.  **Create Virtual Environment:**
    ```bash
    # This should find python 3.11 if it's in your PATH
    uv venv -p python3.11
    # If needed, provide the full path: uv venv -p C:\Path\To\Python311\python.exe
    ```

3.  **Activate Virtual Environment:**
    * In Command Prompt (`cmd.exe`):
        ```cmd
        .\.venv\Scripts\activate
        ```
    * In PowerShell:
        ```powershell
        # You might need to allow script execution first:
        # Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
        .venv\Scripts\Activate.ps1
        ```
    *(Your terminal prompt should now be prefixed with `(.venv)`)*

4.  **Install Python Dependencies:**
    ```bash
    uv pip install -r requirements.txt
    ```

### Running the Application (Windows)

1.  **Ensure the virtual environment is active** (see Step 3 above).
2.  **Run the main script:**
    ```bash
    python main.py
    ```
3.  **First Run Note:** NLTK data downloads may occur automatically.

---

## Installation on macOS

These instructions guide you through installing Incrementum on macOS using Homebrew.

### Prerequisites (macOS)

1.  **Homebrew:** The standard package manager for macOS. If you don't have it, install it by pasting the command from [brew.sh](https://brew.sh/) into your Terminal.
2.  **Xcode Command Line Tools:** Provides Git and C/C++ compilers. Open Terminal (`/Applications/Utilities/Terminal.app`) and run:
    ```bash
    xcode-select --install
    ```
    *(If already installed, it will notify you).*
3.  **Python (Version 3.11 or 3.12 recommended):** While macOS has a system Python, it's best to install a modern version via Homebrew.
    ```bash
    brew install python@3.11
    # Or: brew install python@3.12
    ```
4.  **`uv`:** Install via Homebrew.
    ```bash
    brew install uv
    ```
5.  **Qt6 Libraries:** Install Qt Base and the required modules using Homebrew.
    ```bash
    brew install qt qtwebengine qtcharts
    # `qt` includes base, svg, declarative. WebEngine and Charts are separate.
    ```
    *(Homebrew usually handles PATH setup for installed packages).*

### Installation Steps (macOS)

1.  **Clone the Repository:**
    Open Terminal:
    ```bash
    git clone https://www.github.com/leisrich/incrementum.git
    cd incrementum
    ```

2.  **Create Virtual Environment:**
    Use `uv` and the Python version installed by Homebrew (e.g., 3.11):
    ```bash
    # Homebrew typically makes python3.11 available in the PATH
    uv venv -p python3.11
    ```

3.  **Activate Virtual Environment:**
    ```bash
    source .venv/bin/activate
    ```
    *(Your terminal prompt should now be prefixed with `(.venv)`)*

4.  **Install Python Dependencies:**
    ```bash
    uv pip install -r requirements.txt
    ```

### Running the Application (macOS)

1.  **Ensure the virtual environment is active** (`source .venv/bin/activate`).
2.  **Run the main script:**
    ```bash
    python main.py
    ```
3.  **First Run Note:** NLTK data downloads may occur automatically.
