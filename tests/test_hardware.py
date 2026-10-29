import json

from tuxready import hardware, report
from tuxready.hardware import Device
from tuxready.models import Verdict


def verdicts(devices):
    return {r.item.name: r for r in hardware.check(devices)}


def test_nvidia_needs_driver_and_mentions_hybrid_laptops():
    results = verdicts(
        [
            Device("gpu", "NVIDIA GeForce RTX 4060 Laptop GPU", "10de", "28e0"),
            Device("gpu", "Intel(R) UHD Graphics", "8086", "a788"),
        ]
    )
    nvidia = results["NVIDIA GeForce RTX 4060 Laptop GPU"]
    assert nvidia.verdict is Verdict.TWEAKS
    assert "two graphics chips" in nvidia.summary
    assert "Bazzite" in nvidia.how_to
    assert results["Intel(R) UHD Graphics"].verdict is Verdict.NATIVE


def test_old_nvidia_generations():
    results = verdicts(
        [
            Device("gpu", "NVIDIA GeForce GTX 1060 6GB", "10de", "1c03"),
            Device("gpu", "NVIDIA GeForce GTX 760", "10de", "1187"),
            Device("gpu", "NVIDIA GeForce GTX 1660 SUPER", "10de", "21c4"),
        ]
    )
    assert "580" in results["NVIDIA GeForce GTX 1060 6GB"].summary
    assert results["NVIDIA GeForce GTX 760"].verdict is Verdict.BLOCKED
    assert "580" not in results["NVIDIA GeForce GTX 1660 SUPER"].summary  # Turing: still current


def test_amd_and_wifi_rules():
    results = verdicts(
        [
            Device("gpu", "AMD Radeon RX 7800 XT", "1002", "747e"),
            Device("wifi", "Broadcom 802.11ac Network Adapter", "14e4", "43a0"),
            Device("wifi", "Intel(R) Wi-Fi 6E AX211 160MHz", "8086", "51f0"),
            Device("wifi", "Realtek RTL8852BE WiFi 6 802.11ax PCIe Adapter", "10ec", "b852"),
        ]
    )
    assert results["AMD Radeon RX 7800 XT"].verdict is Verdict.NATIVE
    assert results["Broadcom 802.11ac Network Adapter"].verdict is Verdict.TWEAKS
    assert results["Intel(R) Wi-Fi 6E AX211 160MHz"].verdict is Verdict.NATIVE
    assert results["Realtek RTL8852BE WiFi 6 802.11ax PCIe Adapter"].verdict is Verdict.WORKS


def test_other_rules():
    results = verdicts(
        [
            Device("fingerprint", "Goodix fingerprint", "27c6", "538c"),
            Device("storage", "Intel(R) RST VMD Controller 9A0B", "8086", "9a0b"),
            Device("system", "Microsoft Corporation Surface Laptop 5"),
            Device("system", "LENOVO 21CB"),  # nothing to say about ordinary PCs
        ]
    )
    assert "27c6:538c" in results["Goodix fingerprint"].summary
    assert results["Intel(R) RST VMD Controller 9A0B"].verdict is Verdict.TWEAKS
    assert "linux-surface" in results["Microsoft Corporation Surface Laptop 5"].summary
    assert "LENOVO 21CB" not in results


WINDOWS_JSON = json.dumps(
    {
        "devices": [
            {
                "Name": "NVIDIA GeForce RTX 3070",
                "PNPClass": "Display",
                "PNPDeviceID": "PCI\\VEN_10DE&DEV_2484&SUBSYS_146B10DE&REV_A1\\4&1",
            },
            {
                "Name": "Microsoft Basic Display Adapter",
                "PNPClass": "Display",
                "PNPDeviceID": "ROOT\\BASICDISPLAY\\0000",
            },
            {
                "Name": "Intel(R) Wi-Fi 6 AX201 160MHz",
                "PNPClass": "Net",
                "PNPDeviceID": "PCI\\VEN_8086&DEV_A0F0&SUBSYS_00748086\\3&11583659",
            },
            {
                "Name": "Intel(R) Ethernet Connection I219-V",
                "PNPClass": "Net",
                "PNPDeviceID": "PCI\\VEN_8086&DEV_15BC\\3&1",
            },
            {
                "Name": "WAN Miniport (IP)",
                "PNPClass": "Net",
                "PNPDeviceID": "SWD\\MSRRAS\\MS_NDISWANIP",
            },
            {
                "Name": "Synaptics UWP WBDI",
                "PNPClass": "Biometric",
                "PNPDeviceID": "USB\\VID_06CB&PID_00BD\\4F1",
            },
            {
                "Name": "Windows Hello Face Software Device",
                "PNPClass": "Camera",
                "PNPDeviceID": "SWD\\X",
            },
            {
                "Name": "Intel RST VMD Controller 9A0B",
                "PNPClass": "SCSIAdapter",
                "PNPDeviceID": "PCI\\VEN_8086&DEV_9A0B\\3",
            },
        ],
        "system": {"Manufacturer": "Dell Inc.", "Model": "XPS 15 9510"},
    }
)


def test_parse_windows():
    devices = hardware.parse_windows("﻿" + WINDOWS_JSON)
    found = [(d.category, d.vendor_id, d.device_id) for d in devices]
    assert found == [
        ("gpu", "10de", "2484"),
        ("wifi", "8086", "a0f0"),
        ("fingerprint", "06cb", "00bd"),
        ("ir_camera", "", ""),
        ("storage", "8086", "9a0b"),
        ("system", "", ""),
    ]


def test_parse_windows_single_device_and_empty():
    one = json.dumps(
        {
            "devices": {
                "Name": "AMD Radeon(TM) Graphics",
                "PNPClass": "Display",
                "PNPDeviceID": "PCI\\VEN_1002&DEV_1681\\3",
            },
            "system": None,
        }
    )
    assert [d.vendor_id for d in hardware.parse_windows(one)] == ["1002"]
    assert hardware.parse_windows("") == []


def test_detect_linux_from_fake_sysfs(tmp_path):
    def pci(slot, cls, vendor, device):
        d = tmp_path / "bus" / "pci" / "devices" / f"0000:{slot}"
        d.mkdir(parents=True)
        (d / "class").write_text(cls)
        (d / "vendor").write_text(f"0x{vendor}")
        (d / "device").write_text(f"0x{device}")

    pci("00:02.0", "0x030000", "8086", "64a0")
    pci("00:14.3", "0x028000", "14e4", "43a0")
    pci("55:00.0", "0x010802", "15b7", "5017")  # NVMe: ignored
    usb = tmp_path / "bus" / "usb" / "devices" / "3-7"
    usb.mkdir(parents=True)
    (usb / "idVendor").write_text("27c6")
    (usb / "idProduct").write_text("6594")
    dmi = tmp_path / "class" / "dmi" / "id"
    dmi.mkdir(parents=True)
    (dmi / "sys_vendor").write_text("ASUSTeK COMPUTER INC.")
    (dmi / "product_name").write_text("Example Laptop 14")
    lspci = (
        '00:02.0 "VGA compatible controller [0300]" "Intel Corporation [8086]" '
        '"Arc Graphics 130V [64a0]"\n'
    )

    devices = hardware.detect_linux(tmp_path, lspci)
    assert [(d.category, d.name) for d in devices] == [
        ("gpu", "Intel Arc Graphics 130V"),
        ("wifi", "PCI device 14e4:43a0"),
        ("fingerprint", "Fingerprint reader"),
        ("system", "ASUSTeK COMPUTER INC. Example Laptop 14"),
    ]


def test_hardware_is_not_scored_but_reported():
    results = hardware.check([Device("wifi", "Broadcom BCM4360", "14e4", "43a0")])
    assert report.score(results).percent is None
    assert report.hardware_line(results) == "Hardware: 1 of 1 checked parts need attention."
    assert "HARDWARE" in report.plain(results)
    assert "## Hardware" in report.markdown(results)
