import subprocess
import sys

def test_powershell():
    try:
        result = subprocess.run(['pwsh', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ PowerShell Core available: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ PowerShell Core failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print("❌ PowerShell Core (pwsh) not found")
        return False
    except Exception as e:
        print(f"❌ Error testing PowerShell: {e}")
        return False

if __name__ == "__main__":
    success = test_powershell()
    sys.exit(0 if success else 1)
