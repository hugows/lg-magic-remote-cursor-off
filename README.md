# LG Magic Remote cursor off — memory-only patch

Disable the motion pointer on an LG Magic Remote while keeping directional
buttons and OK working. This is a small, firmware-specific alternative to
injecting a PHP runtime into `lginput2`.

**Tested on one physical TV: LG 43AU801C0SA, firmware 33.31.61,
webOS 25 / 10.3.1-3001.** The owner confirmed that the live patch worked.
Reversal and reapplication were also verified over SSH. The boot monitor has
been installed and started, but persistence across a reboot is **not yet
verified**.

## Compatibility

| Item | Tested value |
| --- | --- |
| TV | LG 43AU801C0SA |
| Firmware | 33.31.61 |
| webOS | webOS 25 / 10.3.1-3001 |
| Target | `/usr/sbin/lginput2`, 32-bit ARM ELF, Thumb functions |
| Executable SHA-256 | `da558f18ff3ec47281fd8f645b9a1f76663c66af44be1dd4607a57cb842c3910` |

The patch refuses to run if the executable hash differs. Matching firmware
numbers or model families alone do not establish compatibility. Do not remove
the hash check or reuse these offsets on another binary.

Root access and Python 3 with `ctypes` are required on the TV. Developer Mode
alone is insufficient. Rooting is a separate operation; this repository does
not root the TV or include a rooting payload.

## What changes

The patch replaces the first four bytes of three functions **in process memory**
with Thumb instructions `movs r0, #0; bx lr` (`00 20 70 47`):

| Function | ELF virtual address | Original first four bytes |
| --- | --- | --- |
| `lginput_uinput_send_position` | `0x66d9c` | `70 b5 8c b0` |
| `lginput_uinput_send_wheel` | `0x6705c` | `2d e9 f0 43` |
| `lginput_uinput_send_custom_event` | `0x67144` | `2d e9 f0 4f` |

This blocks pointer movement, wheel scrolling, and the custom-event path used
for pointer activation. **Wheel scrolling is intentionally disabled too.**
Other custom events passing through the same function are suppressed as well;
voice, every remote feature, and every TV app have not been exhaustively tested.
`lginput_uinput_send_button` is untouched.

The on-disk system executable is unchanged. The script checks its hash,
calculates the ASLR load address, attaches to the current process threads with
`ptrace`, checks the original instructions, writes using `PTRACE_POKETEXT`,
reads them back, and detaches. It refuses to patch if a stopped thread's program
counter is inside a replacement span. Write failures trigger rollback of
already changed words.

A reboot restores the stock executable in memory. If installed, the boot
monitor reapplies the patch after `lginput2` starts or restarts. A firmware
change that changes the executable causes the monitor to stop without patching.

## Try it temporarily

Clone this repository on your computer. Replace `TV_IP` below with the TV's LAN
address. SSH must already work as root. No password or private key is bundled.
The commands use SSH streams because some webOS installations lack `scp`.

```sh
ssh root@TV_IP 'mkdir -p /home/root/magic-pointer'
ssh root@TV_IP 'cat > /home/root/magic-pointer/pointer_patch.py' < pointer_patch.py
ssh root@TV_IP 'python3 /home/root/magic-pointer/pointer_patch.py'
```

Move the remote, then test directional buttons, OK, Home, and the apps you use.
Success prints JSON with `status: patched`. To undo this temporary test:

```sh
ssh root@TV_IP 'python3 /home/root/magic-pointer/pointer_patch.py --restore'
```

Rebooting also undoes the temporary test. A pointer already visible when patched
may remain until the TV hides it. This is not an instantaneous cursor-hide API.

## Reapply automatically

Only install persistence after a successful temporary test. This requires the
rooted Homebrew Channel startup-hook mechanism to be working.

```sh
ssh root@TV_IP 'mkdir -p /var/lib/webosbrew/init.d'
ssh root@TV_IP 'cat > /var/lib/webosbrew/init.d/disable-magic-pointer' < disable-magic-pointer
ssh root@TV_IP 'chmod +x /var/lib/webosbrew/init.d/disable-magic-pointer'
ssh root@TV_IP 'sh /var/lib/webosbrew/init.d/disable-magic-pointer'
```

The monitor checks every five seconds and uses an atomic lock directory to
avoid duplicate monitors. A patch failure stops it. Read its log with:

```sh
ssh root@TV_IP 'cat /home/root/magic-pointer/native-patch.log'
```

## Disable and restore stock behavior

Disable the boot hook and reboot. This stops the monitor and loads the original
process from the unchanged executable:

```sh
ssh root@TV_IP 'chmod -x /var/lib/webosbrew/init.d/disable-magic-pointer; reboot'
```

To re-enable, make the hook executable again and reboot. The small working files
can remain on disk while disabled. If a monitor crashes and leaves a stale
`/tmp/lg-pointer-native.lock`, a reboot clears it.

## Why this approach

The original [disable-lg-magic-remote project](https://github.com/bciuca/disable-lg-magic-remote)
identified the three functions to suppress. Its PHP injection approach did not
work on this TV: the older injector could not resolve glibc's loader functions,
and a newer injector restarted `lginput2` without loading the PHP hook.

This implementation uses Python's standard library and direct `ptrace` writes.
It needs no injected PHP library, Frida runtime, or cross-compilation. The root
setup used during this experiment was [SlopBro](https://github.com/throwaway96/slopbro).
Rooting itself is not part of this patch.

## Reporting another model

Include model, firmware, webOS version, executable hash, and relevant errors.
Do not include pairing keys, passwords, serial numbers, or private keys. A new
binary requires inspecting its symbols and instructions and validating it on
the physical TV before adding support.

## Limitations

This changes a live system service and can disrupt remote input if adapted
incorrectly. Keep working SSH access for recovery. Testing covers one TV and a
live owner-confirmed test; reboot behavior and broader model support remain
unverified. No LG firmware or proprietary executable is distributed here.

MIT license. See [LICENSE](LICENSE).
