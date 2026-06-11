import os
import platform
from subprocess import run


def activate_venv():
    """Activates the virtual environment based on the operating system."""

    venv_path = os.path.join(os.path.dirname(__file__), ".venv", "bin")
    if platform.system() == "Windows":
        activate_script = os.path.join(venv_path, "activate.bat")
    else:
        activate_script = os.path.join(venv_path, "activate")

    if not os.path.exists(activate_script):
        print("Virtual environment activation script not found. Please create the virtual environment first.")
        return

    # For zsh inside tmux (Linux/macOS):
    if platform.system() == "Linux" or platform.system() == "Darwin":
        try:
            run(["tmux", "send-keys", f"source {activate_script}\n"])
            print("Virtual environment activated successfully!")
        except Exception as e:
            print(f"Error activating virtual environment: {e}")
    else:
        # Execute activation script directly for other cases
        try:
            with open(activate_script) as f:
                exec(f.read(), globals())
            print("Virtual environment activated successfully!")
        except Exception as e:
            print(f"Error activating virtual environment: {e}")


if __name__ == "__main__":
    activate_venv()
