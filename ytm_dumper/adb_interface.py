from ppadb.client import Client as AdbClient
from ppadb.device import Device

def read_remote_file(device: Device, remote_glob: str) -> bytes:
    """Reads the content of files matching a glob pattern into buffers."""
    # First, find the file.
    result = device.shell(f"ls -d {remote_glob}")
    remote_path = [line.strip() for line in result.splitlines() if line.strip()]

    if not remote_path:
        raise FileNotFoundError(f"No files found matching '{remote_glob}' on the remote device.")

    # Use 'cat' to read the file content
    result = []
    def handler(conn):
        result.append(conn.read_all())
        conn.close()

    device.shell(f"cat {remote_path[0]}", handler=handler)
    return result[0]

def get_device() -> Device:
    """Returns the first connected adb device."""
    client = AdbClient(host="127.0.0.1", port=5037)
    devices = client.devices()
    if devices:
        return devices[0]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Read a file from adb.")
    parser.add_argument("file", help="Path or glob pattern to the file on the device.")
    args = parser.parse_args()
    read_remote_file(get_device(), args.file)
