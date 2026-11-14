# 🌴 NakhlaGuard — Early Red Palm Weevil Detection

Full working prototype (simulated-data model + web platform + Arduino path): data generation → feature extraction → training →
inference → fusion → AI recommendation → agentic AI assistant → web UI →
low-cost hardware path (Arduino + sound sensor).

**Note on structure**: every file sits in one flat folder (no subfolders) so
the whole project can be dragged straight into a GitHub repo without any
folder-upload issues.

## Quick start

```bash
pip install -r requirements.txt --break-system-packages

# 1) Train the model (auto-generates simulated training data the first time)
python train_model.py

# 2) Set your Gemini key (needed for recommendations + the AI assistant)
export GEMINI_API_KEY="your-key-here"      # Windows PowerShell: $env:GEMINI_API_KEY="your-key"

# 3) Run the server
python app.py
# Open: http://localhost:8000/
```

Without a Gemini key, the server still runs and returns a placeholder
recommendation instead of failing.

To test inference directly without the server:
```bash
python predict.py
```

## Project files

```
app.py                     # Main FastAPI server (all routes)
predict.py                 # Inference on a new audio file
features.py                # Mel-spectrogram-style feature extraction
train_model.py             # Trains the RandomForest severity classifier
generate_synthetic_data.py # Simulated training audio generator
fusion.py                  # Audio+image fusion + Gemini recommendation/report
agent.py                   # Agentic AI: tool-calling loop over farm data
gemini_client.py           # Shared Gemini client with retry + model fallback
severity_labels.py         # Arabic->English label translation for AI output
serial_bridge.py           # PC-side bridge for the Arduino Uno version
nakhla_sensor.ino           # ESP32 + WiFi version of the sensor firmware
nakhla_sensor_uno.ino       # Arduino Uno + USB serial version
index.html / test.html / dashboard.html / palms.html / agent.html / farmers.html
requirements.txt
```

## Deploying on Render

- Build Command: `pip install -r requirements.txt && python train_model.py`
- Start Command: `python app.py`
- Environment variable: `GEMINI_API_KEY` = your key

## Why this design? (originality points)

| Element | Published research (KAUST, Prince Sultan University...) | NakhlaGuard |
|---|---|---|
| Sensor | Distributed fiber-optic sensing — expensive, specialist install | Low-cost sound sensor + microcontroller, self-installed |
| Output | Binary classification (infested/healthy) as an academic result | 4 severity stages → a practical, graded decision |
| Modality | Audio only | Audio + image fusion for higher confidence |
| After detection | Stops at classification | Treatment plan + economic estimate + live alert |
| Interaction | One-shot reading | Agentic AI assistant that queries the farm data itself |

**Important for the presentation**: mention explicitly that you reviewed the
published KAUST and Prince Sultan University research in this area, and that
NakhlaGuard's contribution is turning that research (accurate but expensive)
into a cheap, field-usable tool the farmer can operate themselves.

## What the platform includes

- 4-stage severity classification (Healthy / Early / Moderate / Advanced) with a **confidence score** per result
- AI treatment report (Gemini): diagnosis, 4-week plan, approximate impact estimate
- Photo add-on: palm age estimate + preliminary visual screening (not a diagnosis)
- Palm registry (location, age, history), **QR code per palm** -> live status page (`/palm.html?id=...`)
- Live alerts (WebSocket) + backup contact shown with every alert, 30-day re-check reminder
- Farmer feedback button ("was this result correct?") stored for future retraining
- PDF export of any report (browser print), AI assistant with 5 tools, UI in English / Arabic / Urdu on every page (one language picker in the top bar)

## Arduino / sensor side

- `nakhla_sensor_uno.ino` + `serial_bridge.py` : Uno/Nano -> USB -> PC -> `/predict-full`.
  Run the server in one terminal (`python app.py`) and the bridge in another (`python serial_bridge.py COM5`).
  Close the Arduino Serial Monitor first (it holds the port).
- **Check the timing**: at 115200 baud the sketch cannot really send 4000 samples/s as text lines.
  Time a recording (R to END). If it is longer than ~5.5 s, raise the baud rate (e.g. 250000) in BOTH the sketch and `serial_bridge.py`.
- Nano clones: Board = Arduino Nano, Processor = ATmega328P (Old Bootloader) usually; CH340 driver on Windows.

## Known limitations (be transparent about these with the judges)

1. **The model is trained on simulated data.** The generator mimics periodic larval pulses (about 100-800 Hz) over background noise
   to prove the full pipeline. A public real-recordings dataset exists (**TreeVibes on Kaggle**, 8 kHz; its "infested"
   class also includes other wood-borers). Next step: evaluate the model on it, retrain, then validate on a partner farm.
   The 4 severity stages are an assumption of the simulation; public real data is binary (clean / infested).
2. **RandomForest on hand-extracted features**, not a deep network (limited data). It can be swapped later behind the same
   `predict_severity_from_array` interface.
3. **The sensor/Arduino path is not validated on a real palm trunk.** The prototype uses a sound-sensor module (air microphone);
   the planned field design uses a contact piezo disc. Signal quality through the trunk is unmeasured.
4. **Economic and harvest-impact figures in the AI report are approximate, generated by the model**, not measurements.
5. **No authentication yet**, CORS is open, and the free Render tier can wipe the SQLite database on restart.

## Future steps

- Evaluate/retrain on real recordings (TreeVibes), then a partner farm
- Contact piezo sensor + amplifier, standalone field unit (ESP32), wireless gateway, mobile app, real SMS alerts
- Authentication and permissions; multiple backup contacts

## Testing on real recordings (TreeVibes)

TreeVibes (Kaggle `potamitis/treevibes`, CC0) is ~6 GB zipped. The extracted layout seen on our machine:
`lab\lab\clean`, `lab\lab\infested` (labels in the folder names), `field\field\train`, `field\field\test`, plus `TreeVibes.xlsx`
(folder-level labels for the original folder_1 ... folder_35: AUDIO = 1 means pest sounds). Caveats: "clean" includes non-palm trees, wind and rain;
recordings come from Crete with a drill-bit / waveguide sensor, not our surface piezo.

1. Extract the zip OUTSIDE this folder (e.g. `tar -xf archive.zip -C G:\TreeVibes`). Do not push the data to GitHub.
2. `python train_model.py` (once), then `python eval_treevibes.py "G:\TreeVibes"`
   Labels come from folder / file names (infest, clean, healthy, control) or from folder_N via the xlsx. Unlabelled files are listed as examples so the rule can be adapted.
3. Expect numbers far below the simulated 93%; report them honestly. If poor, retrain a binary model on the real data,
   splitting by tree or by the provided train / test split (never by clip).

## Demo recordings

`python make_demo_wavs.py` writes `demo_wavs/1_healthy.wav ... 4_advanced.wav` (simulated, one per stage; clearest correctly classified clip out of 60 tries)
and prints the answer YOUR trained model gives for each. Say "simulated test recording" when presenting them.

## If the report shows the fallback text instead of Gemini

The page prints "could not reach Gemini" and a canned recommendation when every Gemini attempt fails. `gemini_client.py` now moves to the next model after a timeout
(40 s) instead of giving up. Run `python test_gemini.py` in the same PowerShell window where `GEMINI_API_KEY` is set: it checks the key, the network, the models
available to your key and the response time of each one. The server terminal also prints a line starting with `[NakhlaGuard] Gemini call failed:` with the real reason.

## Training a real-data detector (TreeVibes)

`python train_treevibes.py train "G:\TreeVibes"` trains a healthy / infested detector on the real recordings with the same 44 features the website uses.
Split by tree (never by clip): test = the dataset's own field/test trees plus clean trees 9 and 35; equal weight per tree, balanced classes; the decision threshold
is chosen on out-of-fold predictions of the training trees and applied once to the held-out trees. It prints per-tree results, detection, false alarms and ROC AUC,
and saves `nakhla_binary_model.joblib`. `python train_treevibes.py predict file.wav` classifies one recording with it.
Option `--use-lab 600` adds lab recordings to training. The website itself still uses the 4-stage simulated model until this detector is integrated.

## Baseline check (poster)

`python baseline_check.py` (after `python train_model.py`) reproduces the comparison on the poster: on the same simulated data and the same 75/25 split, a one-feature
energy threshold detects infestation about as well as the Random Forest (93% vs 96% detection) but reaches only 85% on the 4-stage task, versus 93% for the Random Forest.

## Map of visible signs on the trunk (locate.html)

Open `http://localhost:8000/locate.html`. Take or choose 1 to 4 photos of the trunk (front, right, back, left) and enter the approximate trunk height.
Gemini Vision marks EXTERNAL visible signs only (holes, brown ooze, frass, damaged fibres, crown damage) on each photo. The marks are combined on one rotatable 3D trunk
with direction labels and a height ruler, and listed in a table with side and approximate height above the ground. "Print / save PDF" gives a page for an advisor.
The page warns about dark or blurry photos before upload (rough thresholds), and has a shooting guide and an inspection checklist. Backend: `locate.py` + `POST /locate-signs`.

Zoomed second look (checkbox, slower): the server crops a small square around each marked sign (up to 6 per photo) and asks Gemini a strict yes / no / uncertain question about that crop.
Signs answered "no" are faded and left out of the count; "uncertain" ones are kept and labelled. Needs Pillow (`pip install pillow`, listed in requirements.txt). Its effect has not been measured yet:
run `python eval_locate.py "C:\\path\\to\\photos" --verify` on labelled photos (folders named infested / healthy, labels from a confirmed source) and compare the false-mark rate on healthy photos with and without it.

Acoustic hotspot from the sensors (optional): in the vibration-location page (`localize.html`) the button "Show the point on the signs trunk" opens this page with the estimated point
(median of the last ~2.5 s). It can also be typed by hand (x, y in cm on the 40 x 80 cm sensor panel, panel side, panel bottom height, trunk circumference, error, status).
The point is drawn as a red marker (red rings and a filled red dot) on the 3D trunk with an uncertainty ring when an error is given, and the page names the nearest visual sign and its distance in cm.
Agreement (distance up to max(30 cm, 2 x error)) means inspection should start there; it is NOT a confirmation of infestation. The acoustic point is simulated or uncalibrated until it is measured on wood.

Limits, on purpose: it cannot see larvae inside the trunk, it does not say where the weevil is, and it never suggests a pesticide, dose or injection point.
Heights, the angle covered by each photo, the panel placement and the 3D trunk radius are approximations. The "demo" button shows labelled sample data.
`python eval_locate.py "C:\\path\\to\\photos"` reports how often signs are marked on infested photos and the false-mark rate on healthy ones; it does not measure whether a mark is in the right place
(that needs photos with hand-drawn reference boxes).

## Noise and other sounds (wind, rain, other insects, birds, engines)

The 4-stage website model was trained on simulated recordings (pink noise + pulses), so it has seen NO wind, rain, other insects, birds or machinery.
`train_treevibes.py` can add ESC-50 (github.com/karolpiczak/ESC-50, check its licence) as not-infested examples:
`python train_treevibes.py train "G:\\TreeVibes" --noise-dir "G:\\ESC-50-master"`
Categories `wind` and `insects` are held out of training by default and reported as unseen noise (change with `--noise-holdout`).

## Noise filter (so wind, rain, other insects, birds and engines do not raise alerts)

`predict.py` loads `nakhla_binary_model.joblib` if it exists next to it. When that detector says a recording does not look infested, a "moderate" or "advanced"
result is downgraded to "healthy" and no alert is raised. The filter only downgrades, it never creates an alert. It is built with `train_treevibes.py`:

1. Evaluation run (wind and insects are held out, so you see how it behaves on noise it never heard):
   `python train_treevibes.py train "G:\\TreeVibes" --noise-dir "G:\\ESC50\\ESC-50-master" --add-simulated 60`
2. Final run (all noise included in training; this is the file the website uses):
   `python train_treevibes.py train "G:\\TreeVibes" --noise-dir "G:\\ESC50\\ESC-50-master" --add-simulated 60 --noise-holdout none`
3. Restart the server. Settings without retraining (PowerShell, before `python app.py`):
   `$env:NAKHLA_GATE="off"` disables the filter; `$env:NAKHLA_GATE_THRESHOLD="0.5"` makes it more sensitive (lower = fewer suppressed alerts, more noise getting through).

Trade-off: a stricter filter also hides weak (early-stage) signals. `--add-simulated` keeps the simulated demo recordings working. Check every demo file after training.

## Live camera in the signs page, and the adult-insect sign

`locate.html` has a "Open the camera" button: it opens the device camera inside the page (no file upload), shows a dashed frame for the trunk, and "Capture and analyze" takes a frame, sends it to
`/locate-signs`, shows the marks, and moves the side selector to the next side. "Analyze automatically after capture" (on by default) also applies to photos picked from files or taken with the phone camera app.
The live camera needs a secure context: `http://localhost:8000` works on the laptop; a phone opening `http://<laptop-ip>:8000` is blocked by the browser, so the page opens the phone's own camera app instead
(same result, one extra tap). On an https deployment (for example Render) the live camera works on phones.
A new sign type, "adult_weevil" (a clearly visible adult beetle on the trunk, crown or ground), is marked with low or medium confidence unless unmistakable. Larvae inside the trunk can never be seen.

## Teaching the model what other sounds are (wind, cars, birds, ...)

1. Public sounds: `--noise-categories all` uses all 50 ESC-50 categories as "not infested" examples. `python train_treevibes.py cv ... --noise-categories all` prints which categories still fool the model.
2. Your own sensor: `python record_dataset.py COM3 "G:\\my_noise\\wind" --count 30` records clips of one sound type (one folder per type), then add `--own-noise-dir "G:\\my_noise"` to the training command.
   Noise recorded with the same sensor on a trunk is the only data that really tests "wind on a trunk vs weevil in a trunk": ESC-50 was recorded with air microphones, so a model can pass it by recognising the microphone type.
3. No dataset covers every sound. The filter says "infested" only when a recording looks like the pulses it has seen, so an unknown sound can still trigger an alert: keep the alert as a suspicion to be confirmed in the field.

## Sensors -> location -> map inside the pages the customer uses

The map and the camera are no longer a separate page for the customer. `test.html` shows a card "Trunk map" under every analysis result, and `palm.html` shows it under the palm's history;
both embed `locate.html?embed=1` (no header, no demo button, camera only). With an alert result the camera opens by itself; with a healthy result it stays closed.
Where the acoustic point comes from: the bridge (`pc/nakhla_bridge.py` in the Arduino package) sends the average level of the three channels over the last 2.5 s with every recording
(`sensor_rms`, plus `--baseline a,b,c` measured with the sensors quiet; zero by default). `POST /predict-full` estimates the source position with `sensor_location.py`
(same model and numbers as `localize.html`; the two agree on 304 random cases), returns it as `sensor_location`, includes it in the alert, and stores the latest one per palm
(`sensor_locations.json`, read by `GET /palms/{id}/sensor-location` for the palm page). A scan without sensor levels does not change the stored point.

**3D position at inspection and in alerts.** After every check (test.html) and inside every alert card (dashboard.html) the 3D trunk is shown automatically with the estimated vibration-source point (`locate.html?embed=1&view=3d`). With sensors connected the point comes from `sensor_location.py` and is labelled "live, not calibrated" or "calibrated, ± error". With NO sensor levels in the request (for example a sample recording at the exhibition) and a result other than healthy, the server adds a SIMULATED point (`demo_location()`, same palm gives the same point) marked `mode: "demo"`; the page shows a red "demonstration, not a measurement" note. It is never stored as a sensor reading. Set `$env:NAKHLA_DEMO_LOCATION="0"` to switch the simulated point off for real use. The point is the vibration source on the panel, not a confirmed larva position (claim N7 in the register).

**The device is visible in the site.** The home page has a "The device" section (sensors -> Arduino Nano -> bridge -> website, what each part does, prototype status). `test.html` has a "From the device" card and `dashboard.html` a status line, both fed by `GET /device/status`: the last reading that arrived with `sensor_rms`, i.e. from `nakhla_bridge.py` (kept in memory, cleared when the server restarts). The older `serial_bridge.py` does not send `sensor_rms`, so it does not light up that line; use `nakhla_bridge.py` (add `--demo` to try it without hardware).

Honest limits: simulation-tested only; without `sensor_calibration.json` ({"alpha": ..., "gains": [..3..], "error_cm": ...}) the position is marked "not calibrated, accuracy unknown";
the calibration made in the browser page is not shared with the server yet.

**Farmers network (`farmers.html`): request a farmer when you are away.** An owner who is not in the area opens an alert card (or the check result) and taps "Request a farmer"; the request is two steps: (1) the area, typed by the owner (free text, so it stays general; an optional "add my exact location" button attaches GPS coordinates, which cannot be turned into an area name without an outside map service), then (2) when he needs the helper (today / within 3 days / within a week / any time) and what for (inspect / treat or spray / remove an infested palm / other), plus optional palm, notes, his name and number. It is stored in `visit_requests` (columns `when_needed`, `purpose`, `coords` are added to an older `nakhla.db` automatically). Farmers or workers register themselves (`helpers` table); a registered helper enters his number to see open requests and accepts one, and only then does the owner see the helper's name and number under "My requests". The home page shows the real number of registered helpers (`GET /helpers/count`); it starts at ZERO and counts only real registrations, nothing is pre-filled.
Endpoints: `POST /helpers`, `GET /helpers/count`, `GET /helpers` (public list without phones), `POST /visit-requests`, `GET /visit-requests?phone=` (registered helpers only), `POST /visit-requests/{id}/accept`, `GET /visit-requests/mine?phone=`. The POSTs share the per-visitor rate limit; at most 5 open requests per phone.
Honest limits (claim N8): prototype; a phone number is the only "login", numbers (and the optional coordinates) are stored as plain text in `nakhla.db`, nobody's identity is verified, and nothing guarantees a helper in an area or how fast he responds. For the exhibition register only real, willing people (yourself, family, visitors who agree) or test numbers, and say it is a prototype.

## Open demo for visitors (booth mode)

- One navigation for every page (`nav.js`): top bar with the brand and the language button, bottom tab bar (Home, Check, My palms, Alerts, Farmers, Assistant). Arabic is the default language.
- `test.html` is three steps (palm, recording, analysis). Four ready sample recordings (`demo_wavs/`, simulated, labelled as such) let a visitor try it with one tap (`GET /demo-wav/<name>`).
  The result starts with a large verdict banner and one plain sentence of advice (always worded as a suspicion), then the details, the trunk map and the camera.
- Because anyone can open it, `app.py` limits abuse: 20 analysis requests per visitor per minute and 150 for the whole site (`NAKHLA_RATE_MAX`, `NAKHLA_RATE_GLOBAL`), and audio files above 6 MB are refused.
  This protects the Gemini quota behind your key; also set a quota or budget limit for that key in Google AI Studio / Cloud, use a key made only for the exhibition and delete it afterwards.
- The assistant and the palm pages read the database: for a public demo register only demo palms, never real farmers' data.

## Evidence and verification (nothing "from my head")

- `claims.json` is the register of every number and fact: its kind (measured on simulation, measured on real public data, from a published source, or openly NOT claimed), its source with a link, and the command that recomputes it.
- `evidence.html` shows the register inside the site (linked from the home page): the claims, filters by kind, the references with links and a status for each (fully or partly checked, with the date), and the result of the last verification.
- `python verify_all.py` recomputes the measurable numbers in a temporary copy (your deployed models are never touched) and writes `verification_report.html` and `.json`
  with the environment, dataset fingerprints (SHA-256) and PASS / FAIL against the range the register expects. Add `--treevibes "G:\\TreeVibes" --esc "G:\\ESC50\\ESC-50-master"` for the real-data claims, and `--poster file.pptx` to check that the poster's numbers are in the register.
- `references.md` is the reference list for the poster and the written report, generated from `claims.json` and reviewed on 14 November 2026 against each source page: R3 and R9 are marked partial (reason written under them); every other reference was read and the numbers quoted from it were compared. R11 and R18 were removed because they could not be verified.
- The literature says the early phase is much harder than the late one (about 33% sensitivity in one study), so the 80% early recall on simulation (M4) must never be presented as a field result.

## Burst features and sample-rate test (grounded in the literature)

`--features extra` now also computes the burst rate (bursts of 7 to 199 impulses with gaps under 25 ms, as defined by Mankin et al. 2016) and the share of long trains (mostly wind).
`--sr 16000` converts recordings to 16 kHz instead of 4 kHz: if the cross-validation AUC rises clearly, the 2 kHz limit of the node is costing accuracy and a faster sensor board is a priority (analysis only: the website still works at 4 kHz).
