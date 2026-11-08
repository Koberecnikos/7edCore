#!/usr/bin/env python3
"""Fake steamcmd for tests: lists branches and 'installs' a fake 7DTD server."""
import os, sys, time, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
BR = {"public": ("2001", "", "V 3.4.0"), "v3.4.0": ("2001", "Version 3.4.0 Stable", "V 3.4.0"),
      "v3.3.0": ("1900", "Version 3.3.0 Stable", "V 3.3.0"), "v2.6": ("1500", "Version 2.6 Stable", "V 2.6.0"),
      "alpha21.2": ("1000", "Alpha 21.2 Stable", "Alpha 21.2"), "latest_experimental": ("2100", "Latest experimental", "V 3.5.0")}
if os.environ.get("FAKE_PUBLIC_BUILD"):
    nv = os.environ.get("FAKE_PUBLIC_VERSION", "V 3.4.1")
    BR["public"] = (os.environ["FAKE_PUBLIC_BUILD"], "", nv)
    BR["v" + nv[2:]] = (os.environ["FAKE_PUBLIC_BUILD"], "Version " + nv[2:] + " Stable", nv)
a = sys.argv[1:]
if "+app_info_print" in a:
    print('"294420"\n{\n\t"depots"\n\t{\n\t\t"branches"\n\t\t{')
    for n, (b, d, _) in BR.items():
        print(f'\t\t\t"{n}"\n\t\t\t{{\n\t\t\t\t"buildid"\t\t"{b}"\n\t\t\t\t"description"\t\t"{d}"\n\t\t\t\t"timeupdated"\t\t"1760000000"\n\t\t\t}}')
    print('\t\t}\n\t}\n}')
    sys.exit(0)
d = a[a.index("+force_install_dir") + 1]
br = a[a.index("-beta") + 1] if "-beta" in a else "public"
build, _, ver = BR[br]
for p in (10, 55.5, 100):
    print(f" Update state (0x61) downloading, progress: {p} (1 / 2)", flush=True)
    time.sleep(0.2)
os.makedirs(os.path.join(d, "steamapps"), exist_ok=True)
os.makedirs(os.path.join(d, "Data", "Worlds", "Navezgane"), exist_ok=True)
os.makedirs(os.path.join(d, "Data", "Worlds", "Pregen06k01"), exist_ok=True)
shutil.copy(os.path.join(HERE, "server.py"), os.path.join(d, "7DaysToDieServer.x86_64"))
os.chmod(os.path.join(d, "7DaysToDieServer.x86_64"), 0o755)
cfg = "serverconfig_v3.xml" if ver.startswith("V 3") else "serverconfig.xml"   # V3 moved gameplay settings to SandboxCode
shutil.copy(os.path.join(HERE, cfg), os.path.join(d, "serverconfig.xml"))
open(os.path.join(d, "fakeversion.txt"), "w").write(ver)
open(os.path.join(d, "steamapps", "appmanifest_294420.acf"), "w").write(f'"AppState"\n{{\n\t"buildid"\t\t"{build}"\n}}\n')
print("Success! App '294420' fully installed.")
