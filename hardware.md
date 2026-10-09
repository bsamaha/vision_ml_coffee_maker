# Lab computer

The site computer for this proof is a Raspberry Pi 4 Model B Rev 1.5, 4 GB (3.7 GiB reported by the OS). A separate Pi 5 that powers on and then shuts off is not this board and is not set up.

The microSD card is 32 GB. It was rewritten on 9 October 2026 with Ubuntu Server 24.04.5 LTS, 64-bit, image `ubuntu-24.04.5-preinstalled-server-arm64+raspi.img.xz`. There is no desktop. The root filesystem is about 29 GB, with about 25 GB free after the first-boot packages. That meets the Inference note of a 64-bit board with at least 4 GB of RAM and about 20 GB free. Roboflow Inference is not installed yet.

`vcgencmd get_throttled` reported `throttled=0x0` with the webcam attached and the board idle. The supply was holding.

## Login

| | |
|---|---|
| Hostname | `raspberrypi` |
| User | `bs` (sudo, no password prompt) |
| Password | `FrR84cVt7T4cQAggbQr8` |
| SSH key on this PC | `C:\Users\blake\.ssh\raspberrypi_ed25519` |
| MAC | `e4:5f:01:9d:a4:e1` |
| Time zone | America/Chicago, NTP synced |

From this PC, which is on Ethernet:

```bash
ssh -i ~/.ssh/raspberrypi_ed25519 bs@raspberrypi.local
```

`bs` is in the `video` and `plugdev` groups, so `/dev/video0` is usable without extra permissions.

## Network

The Pi is on Wi-Fi. This PC is on Ethernet. Both are on `192.168.1.0/24`, gateway `192.168.1.254`.

On 9 October 2026 the Pi's DHCP address was `192.168.1.248` (`wlan0`) and this PC was `192.168.1.249`. The address can change. `raspberrypi.local` is the stable name. Avahi is installed and was answering.

The Wi-Fi SSID is `ATTTyDDqNP`. The passphrase is only in `network-config` on the card's boot partition.

First boot logged a cloud-init error: `apt` ran once while the clock was still 1 January 1970, before NTP. A retry then installed the packages, and `apt-get update` succeeds now.

Packages from that install: `avahi-daemon`, `v4l-utils` (`v4l2-ctl` 1.26.1), `usbutils`, `ffmpeg`, `python3-venv`, `python3-pip`.

## Webcam

A Sunplus Innovation Technology webcam, USB ID `1bcf:2cb4`, driver `uvcvideo`. It is plugged into a blue USB 3 port. The camera itself is USB 2, so it enumerates at 480 Mbps on the USB 2 companion bus. That is the port to keep using.

| Node | Role |
|---|---|
| `/dev/video0` | Capture. This is the device to open. |
| `/dev/video1` | UVC metadata, not pictures |
| `/dev/video10` and higher | The Pi's own codec and ISP, not the webcam |

`v4l2-ctl --list-devices` names the webcam `Webcam: Webcam (usb-0000:01:00.0-1.1)`.

MJPEG is the format to use. Modes that matter:

| Size | MJPEG rate |
|---|---|
| 2560×1440 | 30 fps |
| 2592×1944 | 30 fps |
| 1920×1080 | 30 fps |
| 1280×720 | 60 fps |

Uncompressed YUYV is much slower (1080p at 2 fps) and is not the capture format.

A test grab on 9 October 2026 wrote a real 1920×1080 JPEG:

```bash
ffmpeg -f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video0 -frames:v 1 frame.jpg
```

The webcam has no zoom and no picture-flip control. The body is mounted upside down. The preview turns the picture upright with `hflip,vflip`. Training stills use that same flip. A second program cannot open `/dev/video0` while the preview is running.

Controls, read on 9 October 2026:

| Control | Value | Meaning |
|---|---|---|
| `focus_automatic_continuous` | 1 | Still automatic. Set to 0 before the training stills, then set `focus_absolute` to the settled value. |
| `auto_exposure` | 3 | Aperture Priority. Manual mode is 1. After switching to 1, set `exposure_time_absolute` or the frame goes dark. |
| `power_line_frequency` | 1 | 50 Hz. This room is 60 Hz, which is value 2. |

## Preview and Nano

The preview is `check/preview.py`. The hook starts it. It listens on port 8080. On this LAN that is [http://192.168.1.248:8080](http://192.168.1.248:8080). The page shows the upright frame and the latest Nano boxes. A person box is green. Other classes are orange. The picture changes about every 5 seconds, which is how long one CPU pass takes.

The interpreter is the slot uv builds from `uv.lock`, under `/home/bs/tank-envs/slots/`. uv is `/home/bs/.local/bin/uv`. The pins are CPU `torch` 2.14.1 and `rfdetr` 1.10.1. Weights are `/home/bs/.roboflow/models/rf-detr-nano.pth` (349 MB). The same `RFDETRNano(device="cpu")` and `predict` call as the desk supervisor. That project refuses to load without CUDA. This one does not.

On 9 October 2026 a 1280×720 frame took about 4.4 seconds after the weights were on disk. The first load, including the download, was about 3 minutes. A later load was about 15 seconds. With the kitchen empty the model returned bowl, chair, dining table, and bottle. No person was in that shot.

`check/nano_person.py` runs three frames against the preview and prints the same log. Roboflow Inference on port 9001 is not installed. The boxed preview is what is running.

# Coffee makers

The proof uses the Ninja in `photos/IMG_1903.HEIC`. The camera looks at the graduated face, a little above the reservoir, with the whole machine in frame. On 9 October 2026 the tank was filled to about 75% and the water showed as a bright horizontal band. The cup marks above that band were readable. The brew procedure is in [technical-solution.md](technical-solution.md).

The model number is on the back of the Ninja, by the power cord. That label is not in the photo, so the notes below are the DCM200 series.

## Ninja Programmable XL 14-Cup

`IMG_1903` is a Ninja DCM200-series brewer: brushed stainless body, black top, glass carafe, and a side reservoir marked up to **14 MAX**. The owner's guide for that series covers DCM200, DCM200A, DCM201, and DCM201BK. The stainless body matches the non-black models in that list. The panel in the photo is H, M, power, DELAY, 1-4 CUP, CLASSIC, RICH, BREW/OFF, WARM, and CLEAN.

Specs from the DCM200-series owner's guide:

| | |
|---|---|
| Power | 120 V, 60 Hz, 1100 W |
| Reservoir | 70 fl oz, removable |
| Carafe | 70 fl oz glass, with a brew-through lid |
| Cup | 5 fl oz. The 14-cup line is 70 fl oz |
| Full-carafe brew | About 12–15 minutes |
| Filter | Permanent filter, or a #4 paper cone |

The reservoir marks are the 2, 4, 6, 8, 10, 12, and 14 cup lines. A Ninja scoop is 2 tbsp, and the chart is one scoop per 2 cups.

### How a brew uses water

Every brew empties the reservoir. CLASSIC, RICH, and 1-4 CUP change the brew cycle. They do not choose a volume. Fill only to the line for the amount you want. The guide states this twice: the unit uses the total amount of water in the reservoir regardless of the 1-4 CUP setting, and the reservoir must not be filled above the 4-cup line when that button is selected.

Each brew starts, pauses, then continues. That pause is the pre-infusion, and its length varies by brew. When the cycle finishes the unit beeps and the clock shows `End`.

The carafe has to be in place. If it is not, the brewer holds the coffee in the brew basket, and that basket can overflow. The carafe also has to start empty. Adding water after a brew or a clean has started is what overflows it.

### Modes

**CLASSIC.** Smooth, well-balanced cup. This is the milder of the two brew styles. A water-only Classic cycle is also how the guide says to prime the machine and to flush it after descaling.

**RICH.** A richer cup that is still smooth. The guide's troubleshooting uses Rich when the coffee is too weak and Classic when it is too strong, and says to change the amount of grounds if the style alone is not enough. Rich is selected instead of Classic, not in addition to it.

**1-4 CUP.** Optimizes the cycle for a batch of 4 cups or fewer. Press it along with CLASSIC or RICH. It does not stop the pump at 4 cups. Water for a 2-cup brew goes to the 2-cup line (10 fl oz). Water for a 4-cup brew goes to the 4-cup line (20 fl oz). Leave this button off for 6 cups and up, and leave it off for a clean cycle.

**DELAY.** Sets a start time. Press DELAY, set the time with H and M, choose CLASSIC or RICH (and 1-4 CUP if the batch is small), then press DELAY or BREW, or wait 5 seconds. DELAY stays lit. Press DELAY again to cancel. The brewer has to stay plugged in. Unplugging it clears the clock, and the delay will not run.

**BREW/OFF.** Starts the brew. Press and hold for 3 seconds to shut the unit off. The unit also shuts itself off after 15 minutes with no interaction.

**WARM.** The warming plate under the carafe. It comes on when a brew starts. The default is 2 hours, and it can be set from 0 to 4 hours. Hold WARM until the clock flashes, then use H or M. On models that have it, the next step sets the plate to High, Medium, or Low. Setting the time to 0 keeps the plate from turning on by itself. Press WARM after a brew to turn the plate off, and press it again to turn it back on. The plate does not use water. If water is added to the reservoir while the plate is in use, the brewer keeps brewing.

**CLEAN.** Descale. Fill to the 14-cup line with coffeemaker descaler, or with 16 oz of white vinegar plus water up to that line. 1-4 CUP must be off. Press CLEAN. The cycle takes up to an hour. Press CLEAN again to cancel, which leaves the machine not fully descaled. Then wash the reservoir and run a full 14-cup Classic cycle with water only. A water-only clean cycle does not descale it. Run a clean when a full carafe starts taking longer than the usual 12–15 minutes.

**H and M.** Set the clock, the delay time, and the warm time. The AM/PM indicator is on the right of the display. The clock in the photo reads 12:35 PM. After a power loss the clock has to be set again.

Some units in this series have a freshness timer that counts up to 4 hours after a brew. The photographed panel has a power button in that spot, so this unit does not have that timer.

## Sources

- Ninja DCM200-series owner's guide (DCM200, DCM200A, DCM201, DCM201BK), 2022: [Home Depot PDF](https://images.thdstatic.com/catalog/pdfImages/f9/f9c1668c-d392-48cd-b020-5cec9a95cef0.pdf)
