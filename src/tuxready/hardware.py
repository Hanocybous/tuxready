"""Hardware check. Device list comes from WMI on Windows and /sys on Linux."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tuxready.models import Item, Kind, Link, Result, Verdict
from tuxready.text import strip_marks

NVIDIA, AMD, INTEL = "10de", "1002", "8086"
BROADCOM, REALTEK, MEDIATEK = "14e4", "10ec", "14c3"
QUALCOMM = {"168c", "17cb"}

# Virtual machine display adapters: QEMU/Bochs, Red Hat (QXL, virtio), VMware, VirtualBox, Hyper-V
VIRTUAL_GPU_VENDORS = {"1234", "1b36", "1af4", "15ad", "80ee", "1414"}

# USB vendors that make (almost only) fingerprint readers.
FINGERPRINT_VENDORS = {"27c6", "138a", "06cb", "10a5", "1c7a", "2808"}

LIBFPRINT = "https://fprint.freedesktop.org/supported-devices.html"
NVIDIA_HOWTO = (
    "Pick a distro that installs NVIDIA's driver for you: Bazzite, Pop!_OS or Linux Mint "
    "(Driver Manager). On Fedora, enable RPM Fusion and install akmod-nvidia."
)

_OLD_NVIDIA = re.compile(
    r"GTX\s*(9\d\d|10[5-8]0)|GTX\s*TITAN\s*X|TITAN\s*Xp|GT\s*10[13]0|Quadro\s*[MP]\d|MX\s*[123]\d0\b",
    re.IGNORECASE,
)
_ANCIENT_NVIDIA = re.compile(r"GTX\s*[4-7]\d\d|GT\s*[4-7]\d\d|Quadro\s*K\d", re.IGNORECASE)
_RAID = re.compile(r"\bRST\b|Rapid Storage|\bVMD\b|Volume Management Device|\bRAID\b", re.I)
_WIRELESS = re.compile(r"wi-?fi|wireless|wlan|802\.11", re.IGNORECASE)
_IDS = re.compile(r"(?:VEN|VID)_([0-9A-F]{4})&(?:DEV|PID)_([0-9A-F]{4})", re.IGNORECASE)


@dataclass(frozen=True)
class Device:
    category: str  # gpu, wifi, fingerprint, ir_camera, storage, system
    name: str
    vendor_id: str = ""  # lower-case hex, e.g. "10de"
    device_id: str = ""


def detect() -> list[Device]:
    try:
        if sys.platform == "win32":
            return parse_windows(_run_powershell())
        if sys.platform.startswith("linux"):
            return detect_linux()
    except Exception:
        pass
    return []


_POWERSHELL = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$classes = 'Display','Net','Biometric','Camera','Image','SCSIAdapter','HDC'
$devices = @(Get-CimInstance Win32_PnPEntity |
  Where-Object { $classes -contains $_.PNPClass } |
  Select-Object Name, PNPClass, Manufacturer, PNPDeviceID)
$system = Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer, Model
[pscustomobject]@{ devices = $devices; system = $system } | ConvertTo-Json -Depth 3 -Compress
"""


def _run_powershell() -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    done = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _POWERSHELL],
        capture_output=True,
        timeout=30,
        creationflags=flags,
    )
    return done.stdout.decode("utf-8", errors="replace")


def parse_windows(text: str) -> list[Device]:
    text = text.strip().lstrip("﻿")
    if not text:
        return []
    data = json.loads(text)
    raw = data.get("devices") or []
    if isinstance(raw, dict):
        raw = [raw]
    devices: list[Device] = []
    for entry in raw:
        name = (entry.get("Name") or "").strip()
        pnp_class = entry.get("PNPClass") or ""
        pnp_id = entry.get("PNPDeviceID") or ""
        ids = _IDS.search(pnp_id)
        vendor, device = (ids.group(1).lower(), ids.group(2).lower()) if ids else ("", "")
        real_hw = pnp_id.upper().startswith(("PCI\\", "USB\\"))
        if pnp_class == "Display" and pnp_id.upper().startswith("PCI\\"):
            devices.append(Device("gpu", name, vendor, device))
        elif pnp_class == "Net" and real_hw and _WIRELESS.search(name):
            devices.append(Device("wifi", name, vendor, device))
        elif pnp_class == "Biometric" and real_hw:
            devices.append(Device("fingerprint", name, vendor, device))
        elif pnp_class in ("Camera", "Image") and re.search(r"\bIR\b|infrared|hello", name, re.I):
            devices.append(Device("ir_camera", name, vendor, device))
        elif pnp_class in ("SCSIAdapter", "HDC") and _RAID.search(name):
            devices.append(Device("storage", name, vendor, device))
    system = data.get("system") or {}
    if system.get("Manufacturer") or system.get("Model"):
        label = f"{system.get('Manufacturer') or ''} {system.get('Model') or ''}".strip()
        devices.append(Device("system", label))
    return _dedupe(devices)


def detect_linux(sys_root: Path = Path("/sys"), lspci_output: str | None = None) -> list[Device]:
    names = parse_lspci(lspci_output if lspci_output is not None else _run_lspci())
    devices: list[Device] = []
    for dev in sorted((sys_root / "bus" / "pci" / "devices").glob("*")):
        try:
            pci_class = (dev / "class").read_text().strip().lower()
            vendor = (dev / "vendor").read_text().strip().lower().removeprefix("0x")
            device = (dev / "device").read_text().strip().lower().removeprefix("0x")
        except OSError:
            continue
        slot = dev.name.split(":", 1)[-1] if dev.name.count(":") == 2 else dev.name
        name = names.get(slot) or f"PCI device {vendor}:{device}"
        if pci_class.startswith(("0x0300", "0x0302", "0x0380")):
            devices.append(Device("gpu", name, vendor, device))
        elif pci_class.startswith("0x0280"):
            devices.append(Device("wifi", name, vendor, device))
    for dev in sorted((sys_root / "bus" / "usb" / "devices").glob("*")):
        try:
            vendor = (dev / "idVendor").read_text().strip().lower()
            product = (dev / "idProduct").read_text().strip().lower()
        except OSError:
            continue
        try:
            label = (dev / "product").read_text().strip()
        except OSError:
            label = ""
        if vendor in FINGERPRINT_VENDORS or "finger" in label.lower():
            devices.append(Device("fingerprint", label or "Fingerprint reader", vendor, product))
    dmi = sys_root / "class" / "dmi" / "id"
    try:
        vendor = (dmi / "sys_vendor").read_text().strip()
        model = (dmi / "product_name").read_text().strip()
        devices.append(Device("system", f"{vendor} {model}".strip()))
    except OSError:
        pass
    return _dedupe(devices)


def _run_lspci() -> str:
    try:
        return subprocess.run(
            ["lspci", "-mm", "-nn"], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_lspci(text: str) -> dict[str, str]:
    """Map PCI slot ('00:02.0') to a readable name from `lspci -mm -nn`."""
    names: dict[str, str] = {}
    for line in text.splitlines():
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        if len(parts) < 4:
            continue
        strip_id = lambda s: re.sub(r"\s*\[[0-9a-f]{4}\]$", "", s)  # noqa: E731
        vendor = strip_id(parts[2])
        vendor = re.sub(r",?\s+(Corporation|Corp\.?|Inc\.?|Co\.,? Ltd\.?)$", "", vendor)
        vendor = vendor.replace("Advanced Micro Devices, Inc. [AMD/ATI]", "AMD")
        model = strip_id(parts[3])
        if re.search(r"\[03(00|02|80)\]$", parts[1]):  # display controllers
            model = re.sub(r"^.*\[(.+)\]$", r"\1", model)  # "AD104 [GeForce RTX 4070]"
            model = re.sub(
                r"^.*\bProcessors?\s+", "", model
            )  # "Core Ultra 200V Series Processors Arc..."
        names[parts[0]] = (model if model.startswith(vendor) else f"{vendor} {model}").strip()
    return names


def _dedupe(devices: list[Device]) -> list[Device]:
    seen: set[tuple] = set()
    unique = []
    for device in devices:
        key = (device.category, device.vendor_id, device.device_id, device.name)
        if key not in seen:
            seen.add(key)
            unique.append(device)
    return unique


def check(devices: list[Device]) -> list[Result]:
    gpus = [d for d in devices if d.category == "gpu"]
    has_integrated = any(d.vendor_id in (INTEL, AMD) for d in gpus)
    results = []
    for device in devices:
        result = _check_one(device, hybrid=has_integrated)
        if result is not None:
            results.append(result)
    return results


def _result(device: Device, verdict: Verdict, summary: str, **extra) -> Result:
    item = Item(name=strip_marks(device.name), kind=Kind.HARDWARE, source=device.category)
    return Result(item, verdict, summary, **extra)


def _check_one(d: Device, hybrid: bool) -> Result | None:
    if d.category == "gpu":
        return None if d.vendor_id in VIRTUAL_GPU_VENDORS else _check_gpu(d, hybrid)
    if d.category == "wifi":
        return _check_wifi(d)
    if d.category == "fingerprint":
        usb_id = f" Its USB ID is {d.vendor_id}:{d.device_id}." if d.vendor_id else ""
        return _result(
            d,
            Verdict.UNKNOWN,
            "Fingerprint login on Linux depends on the exact reader model; many work, some "
            f"don't.{usb_id} Look it up on the libfprint list.",
            links=[Link("libfprint supported devices", LIBFPRINT)],
        )
    if d.category == "ir_camera":
        return _result(
            d,
            Verdict.TWEAKS,
            "Windows Hello face unlock isn't built into Linux. The community tool Howdy can do "
            "it, but setup is manual. The normal webcam works.",
            links=[Link("Howdy", "https://github.com/boltgolt/howdy")],
        )
    if d.category == "storage":
        return _result(
            d,
            Verdict.TWEAKS,
            "Your disk is in Intel RST/RAID mode. Some Linux installers can't see the disk in "
            "this mode. Recent Ubuntu and Fedora usually cope; if the installer finds no disk, "
            "switch the storage mode to AHCI in the BIOS.",
            how_to="Before switching to AHCI, boot Windows once in Safe Mode, or Windows itself "
            "won't start afterwards. Back up first.",
        )
    if d.category == "system":
        return _check_system(d)
    return None


def _check_gpu(d: Device, hybrid: bool) -> Result:
    if d.vendor_id == NVIDIA:
        if _ANCIENT_NVIDIA.search(d.name):
            return _result(
                d,
                Verdict.BLOCKED,
                "NVIDIA no longer supports this card on Linux. It runs with the open-source "
                "driver, but games will be slow.",
            )
        if _OLD_NVIDIA.search(d.name):
            return _result(
                d,
                Verdict.TWEAKS,
                "NVIDIA's newest drivers dropped GTX 900/1000-series cards; the 580 driver "
                "series is the last that supports them. It works, but make sure your distro "
                "installs that version.",
                how_to=NVIDIA_HOWTO,
            )
        text = (
            "Works well for gaming once NVIDIA's own driver is installed, which most distros "
            "don't do by default."
        )
        if hybrid:
            text += (
                " This PC has two graphics chips (NVIDIA + built-in); Pop!_OS and Bazzite set up "
                "switching between them automatically."
            )
        return _result(d, Verdict.TWEAKS, text, how_to=NVIDIA_HOWTO)
    if d.vendor_id == AMD:
        return _result(
            d,
            Verdict.NATIVE,
            "AMD graphics drivers are built into Linux: nothing to install, and great for gaming.",
        )
    if d.vendor_id == INTEL:
        text = "Intel graphics drivers are built into Linux: nothing to install."
        if re.search(r"\bArc\s+[AB]\d", d.name):
            text += " For Arc cards, use an up-to-date distro for the best performance."
        return _result(d, Verdict.NATIVE, text)
    return _result(d, Verdict.UNKNOWN, "Uncommon graphics chip; check it before switching.")


def _check_wifi(d: Device) -> Result:
    if d.vendor_id == BROADCOM:
        return _result(
            d,
            Verdict.TWEAKS,
            "Broadcom Wi-Fi often needs an extra driver that isn't on the install USB, so Wi-Fi "
            "may not work on first boot. Keep an Ethernet cable or phone USB tethering handy. "
            "Linux Mint and Ubuntu offer to install the driver for you.",
            how_to="After installing, look for 'Additional Drivers' / 'Driver Manager', "
            "or install the broadcom-wl package.",
        )
    if d.vendor_id == REALTEK:
        return _result(
            d,
            Verdict.WORKS,
            "Usually works out of the box. A few Realtek Wi-Fi chips have had flaky drivers, "
            "so use an up-to-date distro.",
        )
    if d.vendor_id in {INTEL, MEDIATEK} | QUALCOMM:
        text = "Works out of the box."
        if re.search(r"wi-?fi 7|\bBE2\d\d\b|WCN785", d.name, re.I):
            text += " Wi-Fi 7 chips need a recent kernel, which current distros have."
        return _result(d, Verdict.NATIVE, text)
    return _result(d, Verdict.UNKNOWN, "Less common Wi-Fi chip; search its name plus 'Linux'.")


def _check_system(d: Device) -> Result | None:
    name = d.name.lower()
    if "microsoft" in name and "surface" in name:
        return _result(
            d,
            Verdict.TWEAKS,
            "Surface devices work best with the community linux-surface kernel, which adds "
            "touchscreen, pen and camera support.",
            links=[Link("linux-surface", "https://github.com/linux-surface/linux-surface")],
        )
    if name.startswith("apple"):
        return _result(
            d,
            Verdict.TWEAKS,
            "Intel Macs from 2018-2020 have a T2 chip and need the t2linux kernel; older Macs "
            "usually work with small tweaks.",
            links=[Link("t2linux", "https://t2linux.org")],
        )
    return None
