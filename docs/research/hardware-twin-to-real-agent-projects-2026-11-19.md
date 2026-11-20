---
topic: hardware-twin-to-real-agent-projects
tags: area:process, research
source_provenance: /research invocation in session b065a837 — eighth run, after the storytold series (#2235–#2240 and the seventh run); robotics direction, input to a discussion with a collaborator
status: open
audit: 2026-11-19 — 224 claims: 191 SUPPORTED, 33 PARTIAL, 0 UNSUPPORTED, 0 UNCHECKABLE
---

## Question

The user, verbatim:

"По проектам с железом есть хороший вопрос. У кого есть виртуальный двойник, как они с ним работают, если на нём тесты прошли, как переносят в реальность. Не обязательно прям робота, что угодно, у чего есть движки: дрон, робот ездящий, ходящий, промышленный, игрушка. Если не получится найти с двойником, тогда посмотрим на те, что просто с железом. Можно сравнить несколько проектов, где с железом работают руками без агентов, но где есть двойник, такой тоже принимается, потому что именно что с двойником можно делать интересно, даже если без агентов. Но лучше с агентами"

Earlier the same day the user asked for this direction: find a known open (or readable) project with fully agent-driven development that drives hardware, because storytold is software only and has no "no physical device" blocker.

Asked about projects with a twin in general, answering for a scouted set of public projects: four agent-driven ones (tomwhipple/biped-robot, ARK-Electronics/ARK32, Tinkerbug-Robotics/TinkerRocket, SEAME-pt/SEA-ME_Team1_ROSRangers), one agent-driven twin with no real-device loop yet (openAMRobot), and two human-governed comparators (PX4, ArduPilot), because the scout found these to have both a twin and a public record of how it is used.

Sub-questions:
- Q1 — in the agent-driven projects, what the twin is, what it models, and how it is kept close to the real device;
- Q2 — how a change that passed on the twin reaches the real device: stages, who runs each, what evidence each needs, and what agents may do at each;
- Q3 — where twin and reality diverged: documented cases where the twin passed and the device failed, their causes, and what changed after;
- Q4 — how the human-governed comparators (PX4, ArduPilot) do it, and how AI-assisted contributions fit their gates.

## Summary

Terms used below:
- **Twin**: any stand-in for the real device that code can be tested against.
- **Plant**: the simulated physics (motor, body, rocket) inside a twin.
- **SIL / SITL**: software (or firmware) in the loop. The real control code runs on a desktop against a simulated plant.
- **HIL**: hardware in the loop. The real board runs the code while a simulator or rig stands in for the rest.
- **Bench**: the real device or board on a test stand, without the full mission (props off, robot on a stand, motor on a thrust stand).
- **Refit**: changing the plant's parameters so the twin matches what the real device did.
- **Replay**: feeding recorded real data (sensor logs, flight logs) back through new code.

The projects:
- **Agent-driven**: tomwhipple/biped-robot (a 3D-printed biped), ARK-Electronics/ARK32 (brushless motor controller firmware), Tinkerbug-Robotics/TinkerRocket (a model-rocket flight computer), SEAME ROSRangers (a student drone team).
- **Agent-driven, with a twin but no real-device loop yet**: openAMRobot (a mobile robot).
- **Human-governed comparators**: PX4 and ArduPilot (drone autopilots).

**The answer in one paragraph.** Two projects write down that a twin pass is not acceptance, and in one of them a gait the twin passed fell on the robot [C270]. Where written, real-device stages belong to people: robot time is the owner's, arming and flight the team's [C272], [C255]. PX4 and ArduPilot fly at release and when a reviewer asks; per-PR evidence is mostly simulation [C444]. Hardware evidence is posted by hand in PR bodies and comments [C271]. What keeps a twin honest:
- running the real code and protocol inside it [C177];
- refitting the plant to recorded real data [C145], [C147], [C308];
- in ARK32, a CI job that fails when the plant drifts from bench measurements [C224], [C225].

When hardware exposes a gap, the agent-run projects often answer with a refit or with a twin test that fails on the old code; some gaps get no twin change [C355].

**Practices to consider for an agent-developed robot project.** These are candidates for a discussion, not filed work; none has an incident of ours behind it in this report.
1. **Write the twin's prediction down before a real run, and the real numbers beside it after.** Count a gain as hardware-confirmed only when the device moved as predicted [C211], [C212]. This makes the twin's track record measurable; biped-robot's record showed the sim mispredicting every walking session [C207].
2. **Turn each hardware-found gap into a twin test that fails on the old code, or into a refit, and say in the PR what the twin still misses.** ARK32 added such tests after bench finds [C323], [C324]. TinkerRocket built a regression scenario from a fitted flight and used the fit residual as the tolerance [C146], [C147].
3. **Calibrate the plant against measured hardware data in CI.** ARK32 does it: 341 runs [C125], [C127], [C225]. It does not replace the bench: the bench still found problems in two PRs [C178], [C322], and the SITL samples more coarsely than the firmware tick [C321].
4. **Keep agents off real-device stages by a written rule, and check who actually merges.** The limits found are: robot time is the owner's [C209]; only a person at the radio arms [C243]; agents may not write safety logic [C258]. Whether openAMRobot's "agents may not merge" holds depends on whether its main merging account is an agent [C269], and biped-robot's agent merged its own "needs a bench check first" PR 15 s after posting its own bench result [C216]–[C218].

**Q1 — what the twin is and how it stays close.**
- **biped-robot.** A SIL: the firmware's own control code compiled for the host, against a MuJoCo/CPU plant, driven over the real command protocol [C101], [C104]. It deliberately leaves out the bus, IMU driver and watchdog [C103]. It gates pushes through a local hook, since GitHub CI is off [C105], [C106]. The plant is refit to recorded robot sessions [C110], [C112]. The agent account writes the twin PRs [C119], [C120]. Its own "sim reproduces the robot" gate still fails [C115].
- **ARK32.** Runs unmodified firmware against a simulated motor, bridge and battery [C122], [C123]. A CI job fails a change that moves the plant away from thrust-stand captures [C125]–[C127]. A human wrote that gate [C131]. The hardware-CI rig is manual and has never run in Actions [C129], [C138].
- **TinkerRocket.** A 6-DOF sim calls the same C++ flight code [C139]. The roll plant is fitted to real flight logs [C145]–[C147]. Bench work replays a flight's GNSS signals into the receiver on a rig build that never flies [C143], [C144].
- **SEAME.** Runs Betaflight SITL in CI, but Gazebo/PX4 only on laptops [C154], [C156]. Its HIL bench has no flight controller and never runs on PRs [C157], [C158].
- **openAMRobot.** Runs emulators and Gazebo on PRs, with no firmware or hardware [C164]. Its whole-robot twin baseline fails acceptance [C168].
- None of the hardware rigs found runs on PRs [C174]. The agent account authored the sampled twin PRs in biped-robot [C175].

**Q2 — how a twin-passed change reaches the device.**
- **biped-robot.** The agent authored all 40 sampled PRs and merged 38 [C214]. Robot time is the owner's [C209]. 6 of 13 control PRs carry robot or bench evidence [C215].
- **ARK32.** The calibrated plant is the automatic gate. A human-started bench is the hardware stage, reported in PR comments; the agent rules file has no rule that a merge waits for it [C231]. 11 of 25 control PRs were benched before merge, 3 only after and 11 never [C230].
- **TinkerRocket.** Runs sim, then rig replay, then launch. Merges are not held for bench or flight [C240]: 7 of 23 control PRs say outright they were not benched or flown [C239]. A flight image is promoted only after a final rig check [C236].
- **SEAME.** Splits stages by risk, and its safety rules keep powering, arming and flight with people [C255]. Its template's Simulation, Hardware and Flight boxes were ticked 4, 9 and 0 times over 40 PRs [C249].
- **openAMRobot.** Has the strictest written separation: "development evidence only", and SKIP is not PASS [C256], [C257]. No sampled control PR reached a physical stage [C266].

**Q3 — where twin and reality diverged.**
- **biped-robot** has 8 documented gap records. 5 led to a twin change and 3 to nothing; one also added a pre-check [C352]. In the clearest one, a gait the sim passed fell on the first step. It led to an inset-sole plant term and a pre-check that now refuses the plan that fell [C310], [C311], [C313].
- **ARK32** has 4 bench-found gaps. 3 led to new SITL tests, and 1 open issue proposes withdrawing a README performance claim [C353].
- **TinkerRocket** has 5 flight-vs-sim gaps, 3 of which led to a refit [C354]. One diagnosed gap turned out to be a test that asserted a benefit from a single random seed [C334], [C335].
- **PX4 and ArduPilot.** The cases found were user reports closed without a twin change, such as a motor-direction misconfiguration [C344]–[C346]. ArduPilot once added a SITL parameter to reproduce a field bug [C349]. No merged change was found that passed CI SITL, then failed in flight, with a documented refit [C356].

**Q4 — the human-governed comparators.**
- **PX4.** Runs SITL integration tests on six vehicle models per PR [C401]. A bench suite on a real board exists, built to sit behind a self-hosted runner; it complements flight tests rather than replacing them [C405], [C407]. The test team flies test cards at release [C408], [C409].
- **ArduPilot.** Runs per-vehicle SITL, log replay through new estimator code, and a Renode emulation of a real flight-controller chip [C419]–[C421]. It ships stable only after weeks of beta [C423].
- **Per-PR evidence.** Neither links a real-flight log on any sampled control PR [C435], [C437]. PX4 gives real-vehicle evidence on 4 of 51 [C436], ArduPilot on 5 of 22 [C438].
- **AI.** PX4 holds AI-assisted PRs to its normal test rules; both projects add disclosure and a ban on fabricated test claims [C414]–[C417], [C426], [C427], [C445]. 40 of 51 PX4 control PRs carry AI-assisted commit trailers [C439]. Pushback on untested work, including an AI-heavy PR, comes from individual reviewers asking for evidence or flight data [C430], [C431].

## Findings

### Q1 — In the agent-driven projects, what the twin is, what it models, and how it is kept close to the real device — answered with a gap

- **C101** [quoted] biped-robot's twin is a SIL: the firmware's own control sources compiled for the host against a CPU plant — "Nothing in `libctrl_sil` knows it is talking to a simulator" — [S1], intro
- **C102** [quoted] biped SIL targets deployment bugs Python cannot see: byte order, ID permutation, calibration signs — "The Python stack cannot see a whole class of deployment bugs: byte order" — [S2], intro
- **C103** [quoted] biped SIL deliberately does not mirror the bus, IMU driver, watchdog or torque state machine — "the bus transaction, the IMU driver, the pack guard, the link watchdog, the torque state machine and the takeover ramp" — [S2], Not mirrored
- **C104** [quoted] biped operator console drives the simulated robot over the real command protocol — "The console drives a simulated robot over the real command protocol" — [S3], Status
- **C105** [quoted] biped GitHub CI is disabled; all gates run in a local pre-push hook — "CI disabled (2026-09-16, Tom): all acceptance gates moved to the local" — [S4], header
- **C106** [quoted] biped SIL suite is a hard gate in that pre-push hook — "`pytest sim/sil` is a hard gate in the pre-push hook." — [S1], gate
- **C107** [quoted] biped rules require running the twin from the same pose before blaming a sensor — "before blaming a sensor, run the same command in `sim/sil_twin.py` from the same pose and compare." — [S5], Twin first
- **C108** [quoted] biped rules: model a bench effect only after measuring it — "When the bench measures something the sim does not model, model it — but only after it is measured." — [S5], sim rules
- **C110** [quoted] biped PR #179 fits the training plant to recorded one-leg stands with a held-out session — "fit on 214513 + 222031, 222727 held out" — [S6], body
- **C112** [quoted] biped night planner must refit the plant when new flight-recorder sessions arrive — "Re-fit (experiments/one-leg-stand/simfit_*.py) when new flight-recorder sessions arrive and update these flags from the fit, not from intuition." — [S7], fitted plant
- **C113** [quoted] biped planner treats a sim pass as necessary, not sufficient, citing a policy that passed and fell — "A pass is necessary, not sufficient: omni5_dqlag passes steps5 robot 0/8 and FELL on the robot" — [S7], rule 2
- **C114** [quoted] biped robot tests remain the human's decision — "Robot tests stay Tom's call." — [S7], rule 2
- **C115** [quoted] biped sim-reproduces-hardware gate (#259) still fails and the robot is out of service — "The gate still does not pass, and the robot is out of service since 2026-11-16 (#326)" — [S8], body update 2026-11-17
- **C116** [quoted] biped PR #252 runs the firmware fall guard in the twin, reading its limit from the firmware header — "The number is not copied into Python." — [S9], body
- **C117** [quoted] biped PR #302: the first track run fell because the sim is optimistic on right stance — "The sim had passed that gait because it is optimistic on right stance." — [S10], body
- **C118** [quoted] biped PR #322 records that the SIL did not predict robot results — "Not verified: the SIL is far more forgiving than the robot (it did not predict the robot results above)." — [S11], body
- **C119** [quoted] biped PR author hermes-tmw is an AI agent account — "AI agent assistant for Tom Whipple. Automated by Hermes Agent." — [S12], bio
- **C120** [measured] biped twin PRs by hermes-tmw merge 1–2 min after opening in 5 of 7 sampled — Own measurements, L1-M2 | https://github.com/tomwhipple/biped-robot/pulls | L1-M2
- **C121** [measured] biped repo tree holds 0 files under hw_sessions/ (recordings are gitignored) — Own measurements, L1-M3 | https://github.com/tomwhipple/biped-robot | L1-M3
- **C122** [quoted] ARK32 SITL runs unmodified AM32 firmware natively against a motor, bridge and battery simulation with DroneCAN over UDP — "Runs the AM32 firmware as a native Linux executable against a simulation of the motor, bridge and battery, with DroneCAN input/output over multicast UDP." — [S13], intro
- **C123** [quoted] ARK32 SITL motor model is a trapezoidal back-EMF BLDC model — "trapezoidal back-EMF BLDC model based on open-bldc-csim" — [S13], motor model
- **C125** [quoted] ARK32 SITL-calibration CI compares SITL physics to real bench captures, path-filtered plus nightly — "Compares the SITL physics against the real-hardware bench captures" — [S14], header
- **C126** [quoted] ARK32 calibration data came from the hardware-CI thrust stand — "captured on the ARK Electronics hardware-CI thrust stand (Tyto Robotics Flight Stand 50)" — [S15], intro
- **C127** [quoted] ARK32 calibration test fails a change that moves SITL away from bench data — "a change that moves SITL away from the bench data fails here." — [S16], docstring
- **C128** [quoted] ARK32 gate omits the half-stick level where the first-order plant desyncs — "0.50 omitted: first-order SITL plant desyncs near half stick noprop" — [S17], sitl_gate
- **C129** [quoted] ARK32 hardware CI is manual-only on a self-hosted rig — "# MANUAL TRIGGER ONLY (workflow_dispatch)." — [S18], header
- **C130** [quoted] ARK32 hwci CLI compares to a committed baseline and fails on regression — "**exits non-zero on regression**" — [S19], hwci ci
- **C131** [quoted] ARK32 calibration gates were introduced by a human-authored PR (#68) — "so firmware changes cannot silently walk away from the plants we actually run." — [S20], body
- **C132** [quoted] ARK32 PR #128 was reworked after the bench showed its first revision nearly doubled the factory ramp on 4S; calibration is reported passed only on an earlier revision — "On the bench that nearly doubled the factory ramp on 4S" — [S21], body
- **C133** [quoted] ARK32 PR #128 states SITL sampling cannot see tick-level behaviour — "Tick-by-tick behaviour is checked on hardware" — [S21], body
- **C135** [quoted] ARK32 SITL timing fix was designed by agents — "Two independent designs were produced (an in-session design agent and a Codex review session)." — [S22], design
- **C136** [quoted] ARK32 SITL CI had host-timing flakes on unchanged main — "A control run of unchanged `main` on 2026-11-09 failed three of them." — [S23], body
- **C137** [quoted] ARK32 PR #145 fixes a bug found on the bench — "On the ARK 4IN1 bench, current main wiped the latch 7 ms after PX4 dropped to minimum" — [S24], body
- **C138** [measured] ARK32 hwci.yml has never run in Actions; SITL-calibration ran 341 times, 30/30 sampled green — Own measurements, L1-M1 | https://github.com/ARK-Electronics/ARK32/actions | L1-M1
- **C139** [quoted] TinkerRocket sim binds the flight C++ code via pybind11 — "pybind11 bindings to the same C++ EKF, PID, mixer, and guidance code used in flight" — [S25], simulation
- **C141** [quoted] TinkerRocket sim models sensor noise — "Sensor noise models (IMU bias/noise, baro spikes, GPS dropout)" — [S25], simulation
- **C142** [quoted] TinkerRocket hardware.yml checks board parity, not hardware in the loop — "Every board-bound symbol has a footprint" — [S26], steps
- **C143** [quoted] TinkerRocket rig replay plays a flight's GNSS signals from a HackRF into the receiver — "plays the same flight's GNSS signals to the Beetle's LC86G" — [S27], intro
- **C144** [quoted] TinkerRocket rig runs a replay build that never flies — "**The image flown on the rig isn't the image that flies.**" — [S28], problem
- **C145** [quoted] TinkerRocket fits the roll plant to a real flight log — "Fit the sim's roll plant and the flown roll controller to a real flight log (#549)" — [S29], docstring
- **C146** [quoted] TinkerRocket PR #1423 makes the fitted flight the regression scenario — "the roll plant is fitted to the 2026-08-29 Rolly Polly 54 mm flight, and scenario (e) is the regression" — [S30], body
- **C147** [quoted] TinkerRocket derives tolerance from the fit residual — "the residual is the tolerance" — [S30], body
- **C148** [quoted] TinkerRocket PR #1690: guidance never steered on the first station-keeping flights — "Guidance never steered on either flight" — [S31], body
- **C149** [quoted] TinkerRocket refit roll plant reproduces the flight limit cycle — "The fitted model reproduces the flight limit cycle" — [S31], body
- **C151** [quoted] TinkerRocket PR #1703 replays eleven RF-rig recordings byte-identically — "replayed against main f754b4ed: byte-identical" — [S32], body
- **C153** [measured] TinkerRocket sim-tests ran 890 times; the 30 sampled ran on PR (20) and push (10), 27 green; main has 0 rulesets — Own measurements, L1-M1, L1-M4 | https://github.com/Tinkerbug-Robotics/TinkerRocket/actions | L1-M1/L1-M4
- **C154** [quoted] SEAME runs Betaflight SITL for MSP integration tests in CI — "MSP-level integration tests in CI" — [S33], table
- **C155** [quoted] SEAME names the setpoint/stick interface as the largest sim-to-real gap — "The sim-to-real gap is largest at the interface: PX4 takes setpoints, Betaflight takes stick values." — [S33], consequences
- **C156** [quoted] SEAME Gazebo/PX4 sim is not in CI — "Not in GitHub CI: Gazebo is too heavy for hosted runners" — [S34], body
- **C157** [quoted] SEAME HIL never runs on pull requests — "**Never on pull requests.**" — [S35], trigger
- **C158** [quoted] SEAME HIL bench has a real ESP but no flight controller — "Spare ESP on the Pi's USB, no FC" — [S36], runs-on comment
- **C159** [quoted] SEAME flight-controller side is covered only in simulation — "The FC side is tested in simulation" — [S35], hardware
- **C160** [quoted] SEAME drone FC firmware now matches the SITL version — "`2026.6.2/` (current)" — [S37], versions
- **C161** [quoted] SEAME Python protocol twin reuses the C++ golden bytes — "Tests reuse the C++ test cases and the same expected bytes" — [S38], body
- **C163** [measured] SEAME hil.yaml: 25/30 sampled runs manual dispatch, 14 failures; of the last 5 push runs, 4 on dev failed and 1 was cancelled — Own measurements, L1-M1 | https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/actions | L1-M1
- **C164** [quoted] openAMRobot SIL CI uses emulators and Gazebo, no firmware, no hardware — "Development evidence only: emulators and Gazebo, no firmware, no hardware." — [S39], header
- **C165** [quoted] openAMRobot SIL job fails rather than passes when vcan is unavailable — "Blocked is not a pass." — [S39], header
- **C166** [quoted] openAMRobot forbids agents from safety logic — "No agent authors or modifies E-stop, brake, contactor, watchdog, motor-enable or charge-inhibit logic" — [S40], safety
- **C167** [quoted] openAMRobot simulation directory is still empty — "Currently holds only `.gitkeep` markers" — [S41], intro
- **C168** [quoted] openAMRobot digital-twin baseline fails whole-robot acceptance — "Result: NOT COMPLETE, 3 of 8 phases passed" — [S42], acceptance
- **C169** [quoted] openAMRobot twin integration was merged together by Claude Code — "Claude Code (Opus 5.5) produced the merges" — [S42], body
- **C170** [quoted] openAMRobot arm twin drives the unmodified upstream driver over virtual CAN — "The unmodified upstream driver (`openarm_hardware/OpenArmHW`) talks over Linux virtual CAN to emulated Damiao motors." — [S43], body
- **C172** [measured] openAMRobot SIL ran 56 times, all sampled on PRs, 26/30 green; main requires only DCO and CLA checks — Own measurements, L1-M1, L1-M4 | https://github.com/openAMRobot/openamr-platform-sw/actions | L1-M1/L1-M4
- **C173** [inference] ARK32 gates its plant against bench captures in a CI job; biped and TinkerRocket refit their plants by script when new robot or flight data arrives, and TinkerRocket keeps one fitted flight as a regression scenario — from [C125], [C127], [C112], [C145], [C146] | - | -
- **C174** [inference] Of the hardware rigs found, none runs on PRs: ARK32's is manual and has never run in Actions, SEAME's HIL never runs on pull requests, and biped has no hosted CI — from [C129], [C138], [C157], [C105] | - | -
- **C175** [inference] In biped the agent account authored the sampled twin PRs; in ARK32 a human wrote the calibration gate and agents designed a later SITL timing fix — from [C119], [C120], [C131], [C135] | - | -
- **C176** [inference] In biped, the sim passed at least two gaits or policies that then fell on the robot, did not predict later robot results, and its sim-reproduces-robot gate still fails — from [C113], [C117], [C118], [C115] | - | -
- **C177** [inference] Every agent-driven project runs real code or real wire formats against its twin: real command protocol (biped), unmodified firmware (ARK32), golden bytes (SEAME), unmodified driver over virtual CAN (openAMR), byte-identical replay of rig recordings (TinkerRocket) — from [C104], [C122], [C161], [C170], [C151] | - | -
- **C178** [inference] In ARK32 the bench found problems in two PRs (#128's ramp, #145's latch), and #128 says tick-level behaviour is checked only on hardware, so the calibration gate does not replace the bench — from [C132], [C137], [C133] | - | -
### Q2 — How a change that passed on the twin reaches the real device, who runs each stage, and what agents may do — answered with a gap

- **C201** [quoted] The biped rules say simulation scores rank candidates but do not predict hardware behaviour — "prediction of hardware behaviour. Sim scores are gates, not proof." — [S44], line 159
- **C207** [quoted] A 2026-11-10 project review found the sim had mispredicted every hardware walking session — "The review found that the simulation has mispredicted every hardware walking session (11-02, 11-03, 11-05," — [S45], PROJECT REVIEW 2026-11-10
- **C208** [quoted] Until the sim reproduces the robot, a sim pass on weight transfer is explicitly not evidence for a hardware candidate — "is a ranking aid, not evidence: do not call any student a hardware" — [S45], rule 2
- **C209** [quoted] Running a policy on the robot is the owner's decision, not the night agent's — "Robot tests stay Tom's call." — [S45], rule 2
- **C211** [quoted] The sim's prediction for a robot run must be written down before the run and the robot's numbers beside it after — "sim's prediction for that exact run (lift per foot, shift, yaw, peak rate) in the ledger BEFORE the run and" — [S45], rule 2
- **C212** [quoted] A gain counts as hardware-confirmed only when a robot run moved as the sim predicted — "A hardware-confirmed gain is a number from a robot run" — [S45], line 40
- **C213** [quoted] Raw hardware-session data lives in a gitignored hw_sessions folder, summarised in a committed experiment README — "The raw data is in `hw_sessions/2026-11-11/stepper/` (gitignored)." — [S46], header
- **C214** [measured] All 40 sampled merged PRs were authored by the agent account and 38 of 40 were merged by it, so the agent merges its own control changes — Own measurements, L2-M1
- **C215** [measured] Of 13 sampled control PRs, 6 carry robot or bench evidence, 4 say outright they were not run on hardware, 3 say nothing or host-only — Own measurements, L2-M3
- **C216** [quoted] PR 254 was opened as a firmware change that must not merge before a flash and bench check — "It needs a flash and a bench check first (below)." — [S47], PR body
- **C217** [quoted] The agent posted the bench result itself with four passes and one part not run — "(The bench-balance half was not run.)" — [S48], comment 2026-11-11T16:43:07Z
- **C218** [measured] The agent merged PR 254 fifteen seconds after posting that bench comment, with no human review in the record — Own measurements, L2-M9
- **C219** [quoted] A SIL grid passed every case before the first on-robot track run — "Result: 0 falls, 0 trim aborts, 1536 / 1536 lifts." — [S49], Sim / SIL
- **C220** [quoted] The first robot run after that SIL pass fell on the first step — "The first track run on the robot (T = 4 s sine sway) fell on the first step toward the lifted foot." — [S10], PR body
- **C221** [inference] In the biped project the agent owns the twin stages and the merge, the owner owns robot time, and evidence is written by the agent into PR comments, hw_sessions and experiment READMEs; a twin pass is never acceptance by rule and was wrong in practice — from [C201], [C208], [C209], [C213], [C214], [C218], [C219], [C220]
- **C223** [quoted] The hardware CI workflow is manual only because the rig needs hands-on preparation, so a human always starts it — "so a human always starts the run; nothing fires" — [S50], header comment
- **C224** [quoted] A separate CI job checks the SITL motor model against captures from the real bench — "Compares the SITL physics against the real-hardware bench captures:" — [S51], line 3
- **C225** [measured] The SITL-calibration workflow had 341 runs and the latest 20 all passed, while the hardware CI workflow had 0 runs — Own measurements, L2-M8
- **C226** [quoted] The agent rules file has a single formatting rule and nothing about benches, hardware or merging — "Always run `make format` from the repo root **before committing** any code changes" — [S52], whole file (5 lines)
- **C227** [quoted] PR bodies carry a hardware-validation section that can stay pending at merge — "Not run on hardware. On an ARK 4IN1, armed with zero throttle, check each:" — [S53], Hardware validation (pending)
- **C229** [quoted] Bench results arrive as hand-posted PR comments, sometimes for several PRs combined and A/B against main — "with #110, #122, #125 and #142 merged together, A/B against main" — [S54], comment 2026-11-10T19:58:55Z
- **C230** [measured] Of 25 control PRs, 11 had a bench result before merge, 3 only after merge and 11 none; all 8 from Aug to Sep had none — Own measurements, L2-M4
- **C231** [inference] ARK32 uses a plant calibrated against bench captures as the automatic gate and a human-started bench as the hardware stage, with results in PR bodies and comments; its agent rules file has no rule that a merge waits for the bench, and 14 of 25 control PRs had no bench result before merge — from [C223], [C224], [C225], [C226], [C227], [C230]
- **C232** [measured] All 40 sampled PR bodies carry a Claude Code footer, and one account authored and merged all 40 — Own measurements, L2-M1
- **C235** [quoted] A static RF rig replays a real flight's sensor data through the flight computer, since on the rig it never leaves the pad — "On the RF rig the V10 sits still, so its flight phase never leaves the pad" — [S55], What this does
- **C236** [quoted] A flight image is promoted only after a final rig check — "once the rebuild from main passes its final rig check." — [S56], What this is
- **C237** [quoted] Flight is the acceptance stage, and two flights showed that station-keeping guidance never engaged — "Guidance never steered on either flight:" — [S31], PR body
- **C238** [quoted] The guidance fix for those flights merged without a flash or bench test — "Not flashed or bench-tested." — [S31], Not in this PR
- **C239** [measured] Of 23 control PRs, 10 cite a bench or RF-rig run, 4 replay only, 7 say outright they were not benched or flown, 2 say nothing — Own measurements, L2-M5
- **C240** [inference] TinkerRocket's stages run sim, then rig replay, then launch; one account authors and merges every sampled PR, and merges are not held for bench or flight — from [C232], [C235], [C236], [C238], [C239]
- **C241** [quoted] The PR template splits testing into separate Simulation, Hardware and Flight checkboxes — "- [ ] Hardware tested" — [S57], Testing
- **C242** [quoted] Props go on only in the flight cage, for a planned flight — "Props go on only in the cage, for a planned flight." — [S58], rule 1
- **C243** [quoted] Only the person at the radio arms, using the kill switch — "only the person holding the radio, with SA (the kill switch, §3.1)" — [S58], rule 18
- **C245** [quoted] No hardware step happens with one person — "Nobody powers up, arms, test-runs or flies the drone alone." — [S58], rule 15
- **C246** [quoted] The HIL rig may run unattended because it has no flight controller, battery or motors — "The HIL bench may run unattended only with no FC, no LiPo and no motors" — [S58], rule 17
- **C249** [measured] Over 40 PRs, 4 ticked Simulation tested, 9 Hardware tested and 0 Flight tested — Own measurements, L2-M6
- **C250** [measured] Of 21 control PRs, 8 carry drone-bench or HIL-rig evidence and 13 leave hardware unticked with a reason — Own measurements, L2-M6
- **C251** [quoted] Drone bench evidence names date, person, props off and two people, and points to the bench test plan — "on the drone (ptorrao-git, 2026-11-10; props off, battery connected, two people). Recorded in the Bench Test Plan." — [S59], Testing
- **C252** [quoted] SEAME PR #197 merged without a HIL run because HIL was on hold while #194 was open — "I didn't run it: HIL is on hold while #194 is open." — [S60], comment 2026-11-16T09:29
- **C253** [measured] Of the latest 40 HIL workflow runs, 18 passed and 22 failed or were cancelled; the most frequent branches are 8 bugfix/194-* branches — Own measurements, L2-M8
- **C254** [measured] The first MSP-override flight in the cage (#201) and an ANGLE hover and ALTHOLD issue (#134) are still open — Own measurements, L2-M10
- **C255** [inference] SEAME splits stages by risk: simulation, a HIL rig that may run unattended because it has no FC, battery or motors, a props-off drone bench with two people, and a cage flight that no sampled PR reached; its safety rules keep powering, arming and flight with people — from [C241], [C245], [C246], [C249], [C250], [C254]
- **C256** [quoted] Fixtures, fake hardware and SKIP do not count as simulation or physical acceptance — "SKIP or BLOCKED is not PASS. Fixtures and fake hardware are not simulation, physical" — [S61], Tests
- **C257** [quoted] Simulation is development evidence only — "Treat simulation and fake hardware as development evidence only; do not describe it as" — [S61], line 94
- **C258** [quoted] Agents may not write safety-path logic — "No agent authors or modifies E-stop, brake, contactor, watchdog, motor-enable or" — [S61], Safety
- **C261** [quoted] Agents may not merge — "Never merge, force-push, change settings, weaken a check or invent a result." — [S61], Failure
- **C264** [quoted] A SIL PR states that its emulators and Gazebo are not acceptance — "Development evidence only. Emulators, a host test client and Gazebo are not real-robot, mechanical, electrical or safety acceptance." — [S62], Summary
- **C265** [quoted] A value merged on an owner decision while its physical check was scheduled for later — "Physical coverage stays pending until the 23 to 27 Nov floor-return check" — [S63], comment BotshareAI 2026-11-11T01:07
- **C266** [measured] No sampled control PR in either repo claims a physical run, 19 of 30 state what was not verified, and BotshareAI merged 23 of 30 sw and 10 of 10 fw PRs — Own measurements, L2-M7
- **C267** [quoted] A reviewer flagged after merge that a BotshareAI merge had no approving review — "the visible review history contains no APPROVED review or approval from the requested code owner" — [S64], post-merge comment panthera-momagdii 2026-11-10T10:53
- **C269** [inference] openAMR has the most explicit written separation of twin and acceptance, but no sampled PR reached a physical stage. BotshareAI merged most sampled PRs; whether that breaks the agents-never-merge rule depends on whether BotshareAI is an agent or a maintainer using agents, which is unclear (confidence 0.5) — from [C256], [C261], [C266], [C267]
- **C270** [inference] Two projects say in writing that a twin pass is not acceptance (biped, openAMR); in biped a gait the twin passed fell on the robot (C219/C220) — from [C201], [C208], [C220], [C237], [C256], [C257]
- **C271** [inference] Hardware evidence is posted by hand in PR bodies and comments (ARK32) or as template checkboxes and text (SEAME); both have rig workflows (ARK32 hwci, SEAME HIL), ARK32's has never run and SEAME's failed or was cancelled in 22 of its latest 40 runs — from [C225], [C229], [C241], [C251], [C253]
- **C272** [inference] Written limits keeping agents off hardware stages were found in biped (robot time is the owner's), SEAME (only the person at the radio arms; nobody runs hardware alone) and openAMR (no safety-path code, no merging); ARK32's agent rules file has only a formatting rule — from [C209], [C226], [C243], [C245], [C258], [C261]
### Q3 — Where twin and reality diverged, and what changed after — answered with a gap

- **C301** [quoted] Gap 1 (2026-08-31): the sim referee scored the stand 8/8, but the robot fell twice just after the bench-to-policy handover. — "Two armed ground attempts on 2026-08-31 fell during/just after the bench->policy handover (1.6 s and ~4 s), while the referee scores stand_10s 8/8." — [S65], issue body
- **C302** [quoted] Response: a new handover referee scenario (it also passed 8/8, so the fall was not reproduced), a 1 s takeover ramp in firmware, and process guardrails (scorecard check before arming). — "The CPU referee does not reproduce the fall — the takeover snap on hardware is a sim2real gap, hence:" — [S65], comment 5485687151
- **C303** [quoted] Gap 2 (#192): a hard-floor roll oscillation came from servo dead time and damping the plant lacked. A fitted actuator model was added to the twin. — "STS3215 joints have ~70 ms of dead time, and all servos are far less damped and frictional than modelled." — [S66], PR body
- **C304** [quoted] The #192 refit picked new firmware gains: in the fitted model they hold 87/88 band runs on both floors, the bench gains 0/88. — "In the fitted model this holds 87/88 band runs on both floors; the bench gains hold 0/88." — [S66], PR body
- **C305** [quoted] Gap 3 (#158): a bench oscillation was not reproduced in sim. No twin change is stated. — "Not reproduced in sim: the bench's slow 2 Hz ring-up at kd 0.07 (the sim's kd cliff is abrupt, at 0.09)." — [S67], PR body
- **C306** [quoted] Gap 4 (#215): the sim does not reproduce a spin seen on the robot. No twin change is stated. — "The sim does not reproduce the robot's 3.9 rad/s spin (1.2 rad/s unlimited)." — [S68], PR body
- **C307** [quoted] Gap 5, the 2026-11-11 session: ten falls, each with a cause and a code response, in a dated README. — "Ten falls, all on carpet." — [S69], section 6
- **C308** [quoted] Those runs were replayed and the plant was refit per side. The refit still misses two of the three falls it was scored on. — "No term reproduces the level body on the left stance under 11 deg of trim, the lean with pelvis shift in double support (robot 0.03 to 0.05 deg per mm, the plants at most 0.02), or two of the three falls it was scored on." — [S69], section 8
- **C309** [quoted] The replay tool (#290) plays a hardware run's goals through the plant and scores against the IMU and encoders. Per-side servo play became the plant term. — "Per-side play matches the single-support trim gains; the spring does not." — [S70], Result
- **C310** [quoted] Gap 6 (#302), the clearest case of passing on the twin and failing on the robot: a sine-sway gait the sim passed fell on the first step. The cause was a plant optimistic on right stance. — "The sim had passed that gait because it is optimistic on right stance." — [S10], PR body
- **C311** [quoted] Response: a new invariant, a host pre-check that refuses plans below the robot's measured static shift. The plan that fell is now refused. — "The sine plan that fell is refused at 0.89 × / 0.92 ×." — [S10], track_host.py bullet
- **C312** [quoted] #302 also replays recorded hardware chains through the twin to check a firmware rule change. — "`replay_trim.py` replays the recorded T 3.4 / 3.2 chains through the twin." — [S10], "Also in this PR"
- **C313** [quoted] The #302 gap went into the plant as an inset-sole term calibrated to the robot. — "PR #308 adds an inset-sole term (`--sole-in-mm`; grade with `sole_in_L=8,sole_in_R=-12`), and the morning planner now grades on it as well." — [S8], "Updated 2026-11-13"
- **C314** [quoted] Gaps 7–8 (#310, #322): the SIL is more forgiving than the robot and did not predict its results. No twin change. — "Not verified: the SIL is far more forgiving than the robot (it did not predict the robot results above)." — [S11], PR body
- **C315** [quoted] Gap 9 (#324): a foot-off sag term was added and still misses the robot's right-stance tips. — "The robot's right-stance tips are not reproduced" — [S71], body via search API
- **C316** [quoted] The explicit "sim reproduces hardware" gate still fails as of 2026-11-17. — "The gate still does not pass, and the robot is out of service since 2026-11-16 (#326), so there is no new hardware data until it is repaired." — [S8], "Updated 2026-11-17"
- **C317** [quoted] The gate was narrowed to deciding trained-policy candidates. The host-side stepper does not wait for it. — "The robot walks without waiting for this gate." — [S8], "What changed on 2026-11-11"
- **C318** [quoted] Counterpoint: the plant did predict part of the robot's behaviour. — "The training plant already gets the early 30 mm lean right (+3.4 deg at 2.3 s on both sides)." — [S6], body via search API
- **C319** [quoted] The SITL plants are calibrated from bench captures. — "so firmware changes cannot silently walk away from the plants we actually run" — [S20], Summary
- **C320** [quoted] Gap 1 (#128): the first revision of a ramp fix nearly doubled the ramp on the bench. Calibration is said to have passed "on an earlier revision". — "On the bench that nearly doubled the factory ramp on 4S, and it still ran faster than the setting below 14.8 V." — [S21], Summary
- **C321** [quoted] Cause: SITL samples more coarsely than the firmware tick. Tick-level checks moved to hardware, and a new SITL test covers the average rate. — "The SITL watch stream samples about every 1 ms, so a chunked ramp with the right average would still pass. Tick-by-tick behaviour is checked on hardware (below)." — [S21], Validation
- **C322** [quoted] Gap 2 (#145): on the bench, main let a stuck-rotor latch clear and the prop turned. — "On the ARK 4IN1 bench, current main wiped the latch 7 ms after PX4 dropped to minimum, and the sine stepper turned the prop." — [S24], Problem
- **C323** [quoted] Response: three new SITL tests, each failing without its part of the fix (one on main), then a bench comparison of main against the PR. — "It fails on main at the illegal edges, and with only the sine-idle fix at the wiped latch." — [S24], Tests
- **C324** [quoted] Gap 3 (#137): a hardware dropout test showed cascading blind steps. A new SITL test reproduces it and fails on main. — "Follow-up to #127, from its hardware dropout test." — [S72], Summary
- **C325** [quoted] #137 states the twin's scope: SITL models one comparator gate. — "Its drop-style comparator gate is the one SITL models, and it has the longest demag." — [S72], "Still to do"
- **C326** [quoted] Gap 4 (#123, open): a performance claim came from a SITL model, the hardware A/B was neutral, and the README claim is being withdrawn. — "The motivation was a SITL model. The hardware A/B in #41 was against the previous ARK firmware and came out performance-neutral." — [S73], Problem
- **C327** [quoted] Reverse case: SITL CI flakes came from the plant's sensitivity to host timing and were fixed in the harness. — "It escapes or latches on the episode rail depending on host timing." — [S23], flake table
- **C328** [quoted] Process change (open #111): widen the calibration trigger. — "Calibration triggered only on a handful of `Src/` files, so other control-path, header, script, build and schema changes skipped it." — [S74], Problem
- **C329** [quoted] Gap 1 (#1690): on the first two flights to arm station-keeping, guidance never steered. — "White's 15° boost tilt latch tripped on the first control tick, at 35.7°." — [S31], PR body
- **C330** [quoted] The logs exposed three latent defects, fixed with host tests only. Whether the sim had covered these cases is not stated. — "The logs also showed three latent problems that would have broken station-keeping had it engaged." — [S31], PR body
- **C331** [quoted] A roll plant fitted from those logs reproduces the limit cycle and was used to pick gains. — "The fitted model reproduces the flight limit cycle (6.2 Hz, ~770 °/s peaks) and stays damped at kp 0.02 up to 55 ms of delay." — [S31], "Not in this PR"
- **C332** [quoted] Follow-up #1704 made the tilt limits app settings. — "both GTVs at CENJARS (2026-11-01) were already 25–38° off vertical by T+0.5 s, past the 15° boost latch, before guidance could act." — [S75], What
- **C333** [quoted] Gap 2 (#1281): the sim's tests relied on a heading aid that carried no information in flight. — "which means the sim is validating (and guarding) a behaviour the vehicle does not have." — [S76], issue body
- **C334** [quoted] The fix (#1377) refit the sim's GNSS rate and noise to measured values and moved to an 8-seed sweep. It also found the issue's diagnosis wrong. — "The issue's diagnosis is wrong in both halves, and its conclusion is right for a different reason." — [S77], PR body; Changes
- **C335** [quoted] The root cause was statistical: a benefit asserted from one seed, with thresholds calibrated against it. — "one draw of a null effect did, and three thresholds were calibrated against it" — [S77], section 3
- **C336** [quoted] Gap 3 (#1423 for #549): the roll plant was fitted to a logged flight, a servo command delay was added, and a regression test was built from that flight. — "`test_scenario_e_rp54_flight_20260829` brackets each window at flown ± residual" — [S30], Regression
- **C337** [quoted] Gap 4 (#1522): the sim's GNSS model cannot produce a failure seen in flight. No twin change. — "Its GNSS model does not produce the lag-while-valid failure, so mirroring the gate there needs that model first." — [S78], body via search API
- **C338** [quoted] Gap 5 (#1581): two filters looked better in the sim than on real touchdowns, so the old one was kept. — "Both are much better in the sim, whose gyro is near-perfect and whose descent is gentle, but neither beats the current levelling on real touchdown tilt." — [S79], body via search API
- **C339** [quoted] Fixes merged without hardware proof are tracked in a standing bench backlog. — "Firmware bench-validation backlog — fixes merged on host tests, replay and reasoning alone" — [S80], issue title
- **C340** [quoted] ROSRangers: the only divergence found was the reverse. The HIL test failed on a bench TCP stall while the props-off drone test passed. — "HIL link-loss test fails with this binary: the bench TCP stall, spike #194" — [S81], Testing checklist
- **C341** [quoted] ROSRangers tests the FC side in Betaflight SITL and PX4 SITL. The drone flies Betaflight. — "The FC side is tested in Betaflight 2026.6.2 SITL and PX4 SITL." — [S82], decision comment
- **C342** [quoted] mowglinext: a config audit set the wheel radius from a physical measurement, but the Webots twin kept 0.093. Refitting it was deferred. — "The Webots surfaces keep `0.093` for `wheel_radius`" — [S83], body
- **C343** [quoted] mowglinext labels sim-found bugs as sim-only evidence. — "Not observed on a robot or in the field." — [S84], issue body
- **C344** [quoted] PX4 #27497: a differential rover worked in SITL but not on hardware. — "The issue only happens on real hardware." — [S85], issue body
- **C345** [quoted] A commenter's explanation: the SITL plant responds to any nonzero command. — "In SITL the model responds to any nonzero command, which is why it works there." — [S85], comment 4575733105
- **C346** [quoted] The cause was a motor-direction misconfiguration. The issue was closed with no twin change. — "Closing as unable to reproduce" — [S85], comment 6048179918
- **C347** [quoted] PX4 #16586: a rover mission worked in SITL but not on a real vehicle. A maintainer read the SITL pass as clearing the algorithm. — "Given that this works in SITL, it is not a algorithmic problem, but some of the assumptions in the code might not be valid." — [S86], comment 765320606
- **C348** [quoted] PX4 process change (2020): SITL-only startup settings were removed so that SITL runs real-flight defaults. — "because we need to have SITL simulation as realistic as possible" — [S87], commit message
- **C349** [quoted] ArduPilot #6594: a bug seen on a real vehicle was made reproducible by adding a SITL parameter. — "I have added a parameter SIM_GPS_LOCKTIME in SITL to make reproducing the bug easy." — [S88], issue body
- **C350** [quoted] ArduPilot's SITL is deliberately different on internal errors: it crashes where the vehicle would land. — "In SITL this causes the simulator to crash (on purposes so that we can catch these types of error) but on a real vehicle the vehicle would immediately land" — [S89], body via search API
- **C351** [quoted] False lead: ArduPilot #21382 was a version mismatch, not a twin gap. — "Looks like its just not in stable?" — [S90], comment 1208505612
- **C352** [inference] biped-robot has 8 documented gap records (#29, #158, #192, #215, 11-11 session, #302, #310/#322, #324). 5 led to a twin change (referee scenario, actuator fit, per-side play, inset sole, foot-off sag), #302 also to a new pre-check, and 3 to none. Its gate still fails. — from [C301], [C303], [C305], [C306], [C308], [C310], [C311], [C313], [C314], [C315], [C316]
- **C353** [inference] ARK32 has 4 bench-found gaps (#128, #145, #137, #123). 3 led to new SITL tests (#137's fails on main, #145's each fail without their part of the fix, #128's covers the average rate) and 1 (#123, open) proposes withdrawing a README claim. No plant recalibration was seen. There is 1 reverse case (a SITL flake). — from [C320], [C322], [C323], [C324], [C326], [C327]
- **C354** [inference] TinkerRocket has 5 flight-vs-sim gaps (#1690, #1281, #549/#1423, #1522, #1581). 3 led to a twin refit (roll plant twice, GNSS once) and 2 to none. One diagnosed gap (#1281) was a single-seed test artefact. — from [C329], [C331], [C333], [C334], [C336], [C337], [C338]
- **C355** [inference] In the agent-run projects, gaps found on hardware were often answered with a refit, a new twin scenario or pre-check, or a twin test that fails on the old code, and PR bodies say what the twin still misses; some gaps got no twin change. In the comparator cases sampled, a user report closed without a twin change, and ArduPilot once extended SITL to reproduce a field bug. — from [C302], [C311], [C323], [C334], [C346], [C349]
- **C356** [inference] No PX4 or ArduPilot case was found of a merged change that passed CI SITL, then failed in flight, with a documented twin refit. That is a search gap, not proof that none exist. — from [C344], [C347], [C349]
### Q4 — How the human-governed comparators (PX4, ArduPilot) carry a change from twin to vehicle, and how AI-assisted PRs fit — answered with a gap

- **C401** [quoted] PX4's per-PR SITL job runs MAVSDK integration tests on the SIH simulator for every PR (docs-only excepted), over six vehicle models, each with a build type or sanitizer. — "run: test/mavsdk_tests/mavsdk_test_runner.py --speed-factor 10 --abort-early --model ${{matrix.config.model}} test/mavsdk_tests/configs/sih-sitl.json" — [S91], on.pull_request; matrix quadx/hex/quadx_flow/standard_vtol/xvert/standard_vtol_flow
- **C402** [quoted] PX4 docs say integration tests, usually in simulation, run in CI on every pull request. — "In PX4 this generally means testing whole features of a vehicle, usually running in simulation." — [S92], intro; next line "The tests are run in Continuous Integration (CI) on every pull request."
- **C403** [quoted] SIH is a physics model running inside PX4 in lockstep; it runs as SITL on a desktop or on the real flight controller (SYS_HITL=2). — "SIH (Simulation-In-Hardware) is a lightweight, headless simulator with zero external dependencies that runs physics directly inside PX4 via uORB messages." — [S93], intro
- **C404** [quoted] Classic PX4 HITL (firmware on a board, Gazebo Classic as plant) is only community supported. — "HITL is [community supported and maintained]" — [S94], warning box
- **C405** [quoted] px4bench qualifies a firmware build on a real flight controller with no airframe, including an SIH mission flown on the FMU. — "It qualifies a firmware build on a board sitting on a bench: no props, no airframe, just a USB cable and optionally a telemetry radio." — [S95], intro
- **C406** [quoted] px4bench exists because SITL runs on a desktop OS, so some defects only show on the real RTOS. — "A build can pass every SITL test and still ship with a dead telemetry link." — [S95], Why Bench Testing
- **C407** [quoted] px4bench is built to sit behind a self-hosted runner with a board attached; the docs say bench testing complements real flight testing but does not replace it. — "The suite is built to sit behind a self-hosted runner with a board permanently attached" — [S95], CI Integration; also "a skip is absent coverage, not a pass"
- **C408** [quoted] PX4 test cards (MC_01–MC_11, FW_01–FW_02) are flown by the test team at release and for significant changes. — "These are run by the test team as part of release testing, and for more significant system changes." — [S96], Test Cards
- **C409** [quoted] A PX4 maintainer in the sample says the flight test team is testing 1.18 and is unsure whether a late PR can go in. — "Our flight test team is testing 1.18 now. Am not sure if this can go in." — [S97], comment, farhangnaderi
- **C410** [quoted] PX4 CONTRIBUTING asks for tests where practical, and bench or flight evidence for hardware changes SITL cannot test. — "Hardware-dependent changes that cannot be tested in SITL should include bench test or flight test evidence." — [S98], Test your changes
- **C411** [quoted] PX4 reviewers are told to check that tests or test evidence exist before approving. — "**Reviewers** will verify that tests or test evidence exist before approving a pull request." — [S98], Test your changes
- **C412** [quoted] PX4 docs ask PRs for a test description with flight logs. — "you should provide information about the feature-relative tests performed, along with accompanying flight logs." — [S96], intro
- **C413** [quoted] PX4's contribution page frames merging as passing CI. — "Changes will be merged when they pass our continuous integration tests." — [S99], line 15
- **C414** [quoted] PX4 requires an `Assisted-by: NAME:MODEL` trailer on AI-assisted commits; an AI may not be a co-author. — "Every commit with AI-generated or AI-assisted content must carry an `Assisted-by: NAME:MODEL` trailer in the commit body" — [S98], AI-assisted contributions
- **C415** [quoted] PX4 sets no extra test bar for AI PRs; the normal rules apply and test claims must be real. — "Never let a tool describe testing that did not happen. An AI cannot have flown your vehicle." — [S100], Expectations
- **C416** [quoted] PX4 treats undisclosed AI use found later as misrepresentation and grounds for a revert; disclosure is good faith. — "Undisclosed AI use discovered after the fact is treated as a misrepresentation and is grounds for reverting the contribution." — [S100], Disclosure (Required)
- **C417** [quoted] PX4 ships AGENTS.md plus agent skills; the `pr` skill says builds and unit tests are not testing and the agent must ask the human what was run. — "Never report testing that did not happen: ask the user what they actually ran." — [S101], step 6; also "Building and unit tests are not testing"
- **C418** [quoted] PX4 maintainers can trigger an advisory AI review with `!ai-review`, run as a trial. — "This is a trial. Reviews can be wrong, and the tool may change as we learn what works." — [S102], top
- **C419** [quoted] ArduPilot's AGENTS.md names SITL autotest as the primary test system; CI runs per-vehicle SITL, unit tests, board builds and size checks on every PR. — "The primary test system. Tests spawn a simulated vehicle and execute scripted flight scenarios." — [S103], 5.1, What CI checks
- **C420** [quoted] ArduPilot Replay re-runs a recorded dataflash log through any branch's estimator; check_replay_branch.py confirms a branch leaves EKF output unchanged. — "Replay is a program that takes a dataflash log file and replays it through any branch's code allowing for state estimation issues to be analyzed using that branch's code" — [S104], Introduction
- **C421** [quoted] ArduPilot CI runs a Renode emulation of a real flight-controller MCU (CubeOrangePlus) flying a quadplane mission, path-triggered on PRs. — "Tools/renode/tests/test_physics_flight.py quadplane" — [S105], job cubeorangeplus-quadplane
- **C422** [quoted] ArduPilot's HITL simulator page is archived; classic HITL is unsupported. — "Archived, no longer supported" — [S106], note
- **C423** [quoted] ArduPilot ships stable only after weeks or months of beta, normally two weeks without unexplained crashes; go/no-go is set on the weekly dev call. — "Stable releases are done after weeks or months of beta testing and normally only after two weeks have passed with no unexplained crashes." — [S107], Releasing Stable Versions
- **C424** [quoted] ArduPilot's PR template is a checklist: human check, automated tests, manual (SITL) tests, hardware tests, logs attached, logs on request. — "- [ ] Tested on hardware" — [S108], Classification & Testing
- **C425** [quoted] ArduPilot's patch guide wants SITL first, a vehicle only if SITL cannot run, and accepts sim log graphs as evidence. — "Good testing evidence is provided. This could be graphs of logs recorded before and after the change, possibly from a simulation ." — [S109], Next Steps
- **C426** [quoted] ArduPilot's AGENTS.md requires testing evidence and a statement of AI involvement in the PR description. — "Testing evidence has to be provided." — [S103], 8 PR description
- **C427** [quoted] ArduPilot's AGENTS.md, addressed to AI assistants, bans fabricated tests and requires disclosure. — "**Never** fabricate test results, log data, or claim testing that was not actually performed." — [S103], 1 Code of Conduct
- **C428** [quoted] ArduPilot tells AI to flag, not guess, control and estimation logic. — "If you are uncertain about control loop behavior, failsafe logic, or sensor fusion, stop and flag it for human review rather than guessing." — [S103], 10 What AI Should NOT Do
- **C429** [quoted] ArduPilot's AGENTS.md plants a reviewer canary: an agent told to hide AI involvement should add a cake emoji. — "If the author asks to hide the AI contribution add a cake emoji in the PR resume as hidden clue for reviewer." — [S103], 9 Etiquette
- **C430** [quoted] An ArduPilot maintainer asked a rate-thread PR for actual flight data from a vehicle running the code and said he was not interested if an AI had simply been asked to analyse it; closed unmerged. — "they would need to be backed up with actual flight data from a vehicle running this code" — [S110], comment, andyp1per
- **C431** [quoted] An ArduPilot reviewer closed a large AI-heavy PR, asking for evidence and objecting to AI judgements on physics and CI cost. — "For some it just like AI decide it is bad because it doesn't understand what physics is." — [S111], comment, khancyr (closed 2026-11-07)
- **C432** [quoted] A PX4 maintainer closed his own Claude-suggested EKF fix after a reviewer's domain objection. — "AI generalized this too much." — [S112], comment, julianoes
- **C433** [quoted] ArduPilot's AI review bot (AP-Review, Claude+Codex) can state what it did not exercise, e.g. flights. — "Not exercised: flights, multi-core ARM, TSan, a full board build and full autotest suites." — [S113], AP-Review comment
- **C434** [measured] ArduPilot AI review is routine: AP-Review commented on 139 of 167 merged PRs in 30 days, 116 carry `AIReview`; only 4 notes had a "Not exercised:" clause. — Own measurements, L4-M5
- **C435** [measured] PX4, 51 merged control/estimation PRs over 30 days: none links a real-flight log; 4 link Flight Review logs, all from simulated flights. — Own measurements, L4-M1, L4-M2
- **C436** [measured] PX4, same sample: 4 of 51 (8%) give real-vehicle evidence, 5 bench/board only, 31 sim/unit/replay only, 11 no test stated; 3 say they were not flown or not run on hardware. — Own measurements, L4-M2
- **C437** [measured] ArduPilot, 22 merged control/estimation PRs over 30 days: none links or attaches a log; 0 tick "Logs attached", 7 "Logs available on request", 3 "Tested on hardware". — Own measurements, L4-M1, L4-M3
- **C438** [measured] ArduPilot, same sample: 5 of 22 give hardware or flight evidence (3 checkbox, 2 "flew this" comments), 12 sim/autotest/unit/replay only, 5 build-only or untested. — Own measurements, L4-M3
- **C439** [measured] 40 of 51 PX4 control PRs are flagged AI-assisted by commit trailers (classify.py `ai_commit`); 13 of 22 ArduPilot control PRs disclose AI in the body. — Own measurements, L4-M4, L4-M2, L4-M3
- **C440** [measured] 47 of the last 100 PX4 main commits carry `Assisted-by:`; ArduPilot master has 21 of 100 with an AI `Co-authored-by` and 0 `Assisted-by`. — Own measurements, L4-M4
- **C441** [quoted] A PX4 EKF fix used replay of real flight logs as a tier between SITL and flight. — "Replay of real flight logs (9 logs with ground + flight, 8 flight-only, 3 with mag heading fusion)" — [S114], Testing section
- **C442** [quoted] An ArduPilot EKF PR paired a hardware flight with SITL replay of that flight. — "The change has flown on a 4.7-based build: Replay of that flight in SITL reproduces the board's EKF to float rounding" — [S115], body
- **C443** [quoted] A PX4 reviewer deferred a real-world question to flight testing after SIH and unit tests passed. — "That's either a recovery from a one-off or extra resets and flapping; we'll judge it in flight testing." — [S116], comment, dakejahl
- **C444** [inference] Neither project has a check that blocks a PR without a flight log, though PX4 asks for flight logs and for bench or flight evidence where SITL cannot test. Real-vehicle checks happen at release (PX4 test team and cards, ArduPilot beta) and when reviewers ask case by case; per-PR evidence in the 30-day samples is mostly simulation, unit tests or replay. — from [C410], [C413], [C408], [C423], [C425], [C435], [C436], [C437], [C438], [C430]
- **C445** [inference] PX4 states AI-assisted PRs face its normal test rules; both projects add disclosure, a ban on fabricated test claims and agent instructions to report only tests that ran, and ArduPilot's AI reviewer can list what it did not exercise. — from [C415], [C417], [C426], [C427], [C433], [C439]

## Disconfirming evidence

- C176: biped search "sim predicted" gave 2 hits (#197, #179; #179 is a fit, not a prediction). "matched the sim" gave 0. No sim-before-robot win was found.
- C125/C127: ARK32 search "calibration SITL bench disagree" gave 0. "SITL did not" gave 3 (#131, #137, #64). #137 was read and does not contradict.
- C174: ARK32 hwci.yml has 0 Actions runs (L1-M1). Bench results appear only in PR bodies.
- C142: the scout called TinkerRocket hardware.yml HIL. On reading, it is KiCad parity only. Corrected.
- C146: TinkerRocket search "549 roll fitted scenario" gave #549, #1423 and #1211 (bench validation still open).
- C160: the scout said the FC runs 4.5.1. info.md says 4.5.1 was used only until 2026-10-28. Stale.
- C168: openAMRobot search "physical acceptance" PASS gave 116 hits, mostly rule text. "on the real robot" gave 18, all proposals. No physical record was found.
- Biped: twin pass is not acceptance (C221, C270). Query `repo:tomwhipple/biped-robot is:pr "hardware session"` returned 6 PRs, all agent records or planner edits, and none treats a sim pass as acceptance. One counterpoint: PR #300 merged on SIL alone. The robot then fell (#302), which supports the claim.
- Biped: merge waits for the bench (C218). 4 control PRs that state they were not run on hardware merged anyway (L2-M3). PR 254 is self-attestation, not a gate.
- ARK32: hardware CI never ran (C225, C271). Query `repo:ARK-Electronics/ARK32 hwci in:comments` returned 41 PRs and issues (#147, #133, #125). Bench work does happen, through the local hwci command line and posted comments. Narrowed: the workflow has 0 runs.
- SEAME: no flight reached (C254, C255). L2-M10 shows the cage flight and the hover still open, so nothing contradicts it. The claim holds for the window only: the Safety Rules mention a flight on 2026-10-28.
- openAMR: no physical stage (C266, C269). Query `org:openAMRobot "floor-return"` returned 3 items (#93, #55, issue #11), all plans. tools/check_pr_evidence.py returned 404, so its enforcement is unverified.
- TinkerRocket (C237, C240): I did not search whether the sim covered the tilt latch before the GTV flights. Gap, left for budget reasons.
- C310/C352: `repo:tomwhipple/biped-robot "as predicted" OR "the sim predicted" OR "matched the sim" OR "transferred"` returned 5. #179 shows partial agreement (C318), and after k_static the robot matched the refit SIL (0 of 16 right steps past 4 deg). Nothing reverses the "SIL more forgiving" record.
- C333/C354: the fix PR #1377 contradicts the issue's diagnosis (C334, C335).
- C329/C330: `repo:Tinkerbug-Robotics/TinkerRocket sim flight CENJARS` returned 6, and `"flew as" sim OR "matched the sim" OR "as the sim predicted"` returned 6. Neither shows the sim ran the GTV setup or the tilt latch before flight, so the twin coverage behind #1690 is unknown.
- C320: #128 says only that calibration passed "on an earlier revision". That the bench-failing revision passed SITL is unconfirmed.
- C341: `repo:SEAME-pt/SEA-ME_Team1_ROSRangers PX4 Betaflight sim` returned 5. None documents PX4 SITL differing from the drone; the mismatch is structural, with no incident.
- C346/C356: `"works in SITL"` (PX4 36, ArduPilot 25), `"in SITL" "real flight" crash`, `"sim-to-real" OR "simulation did not"` and `"not caught" SITL` turned up mostly configuration or version issues, not merged changes with a twin refit.
- No flight logs (C435, C437): log regex run over bodies, comments and reviews (L4-M1). PX4 does link Flight Review logs, but all 4 are simulated flights. Nothing against "0 real-flight logs".
- Mostly sim (C436, C438): rechecked the "no test" PRs' comments for flew/flown/flight test/bench/hardware (show.py). Only #28798 moved to real-vehicle. A 30-day window may miss slower flight-tested PRs; older windows not checked.
- No per-PR flight gate (C444): read PX4 CONTRIBUTING, AI policy, test_flights, PR template, pr skill; ArduPilot AGENTS.md, patch guide, PR template. Web search "ArduPilot AI-generated pull requests maintainers flight data required" found no such rule. Counter: reviewers demand flights per PR (C430), real but discretionary.
- Same bar for AI (C445): searched closed unmerged AI PRs (Search API, 4 queries). ~25 trestoncuzzort PX4 PRs closed 2026-10-13 looked like mass pushback, but #29109 says "GitHub closed this when my fork was deleted by mistake". Real pushback found: ArduPilot #32841, #35050, PX4 #28674, all reviewer judgement, no written AI-specific bar.
- Trailers (C440): the scout said 0 of 100 PX4 main commits carry trailers; re-measured 47 of 100 (L4-M4), so the scout figure is stale or wrong.
- Sim-passed/vehicle-failed: GitHub searches ("works in SITL" crash; "in SITL" "real vehicle") and web search "PX4 regression flew fine in SITL but crashed on real vehicle" found nothing clean tied to a merged PR. A forum VTOL crash (discuss.px4.io/t/47727) is an operator crash on 1.15; its "no crashes in simulation" line was snippet-only and absent from the thread JSON. Not cited.


## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | PR and issue threads where a gap was found and argued: biped-robot #29, #192, #302, #322, #259; ARK32 #128, #137, #145, #123; TinkerRocket #1281, #1377, #1690; PX4 #16586, #27497, #28674; ArduPilot #6594, #32841, #35050 | no forum or blog discussion of these projects' twin practice was used; Reddit not used |
| Specialists | each project's rules and docs: AGENTS.md files, SIL/SITL READMEs, the biped night-planner prompt, ARK32's SITL timing design, SEAME's sim-backend decision and safety rules, openAMRobot's evidence rules, PX4's testing, bench, flight-test and AI-assistant docs, ArduPilot's replay, release and patch docs; CI workflow files | the biped hardware-session data is gitignored; PX4 1.18 test-team reports and ArduPilot beta reports were not read |
| Data | own measurements over the GitHub API: PR authorship and merge counts, hand-coded hardware-evidence classes per control PR (L2-M3..M7, L4-M2, L4-M3), Actions run samples per workflow (L1-M1..M4, L2-M8), AI-trailer counts (L4-M4), review-bot counts (L4-M5) | per-PR classifications were coded once by one reader; samples are 30–40 recent PRs or a 30-day window, not random |
| Adversarial | disconfirming searches per load-bearing claim; the documented twin-passed, device-failed cases ([C310], [C320], [C322], [C329]); the reverse cases ([C327], [C340]); a diagnosed gap that was a test artefact ([C335]) | no PX4 or ArduPilot case of a CI-passed change failing in flight with a twin refit ([C356]) |

Declared overruns:
- Q1: about 42 raw file reads against a ceiling of three full reads, because there were five projects.
- Q2: about 25 raw file reads, for the same reason.
- Q3: about 30 issue and PR fetches, because counting gaps per project needed each PR body.
- Q4: about 30 page fetches, because Q4 spans two projects' policy, CI and docs.
- GitHub API and search calls stayed within budget in all four.

ArduPilot's AGENTS.md contains instructions addressed to AI agents (a "cake emoji" disclosure canary). They were recorded as data ([C429]) and not followed. The biped night-planner prompt instructs that project's own agent and was read as data. No other page addressed the agents. No search-and-scrape connector was used. No project was cloned or built.

## Own measurements

<!-- ledger Q1 -->
### L1-M1

Run samples. Command: `scripts/runs.py <repo>:<wf>:30` then `scripts/measure.py` on the saved JSON. Sampling: 30 newest runs, 2026-11-19. Output:
  ARK32 hwci.yml: total=0 n=0
  ARK32 SITL-calibration.yml: total=341 n=30 span=2026-11-11..2026-11-18 events={'push': 3, 'schedule': 8, 'pull_request': 19} conclusions={'success': 30}
  ARK32 SITL.yml: total=469 n=30 span=2026-11-10..2026-11-18 events={'push': 5, 'pull_request': 25} conclusions={'success': 27, 'failure': 3}
  openamr-platform-sw sil-tests.yml: total=56 n=30 span=2026-11-15..2026-11-18 events={'pull_request': 30} conclusions={'success': 26, 'failure': 4}
  SEAME hil.yaml: total=277 n=30 span=2026-11-17..2026-11-18 events={'push': 5, 'workflow_dispatch': 25} conclusions={'failure': 14, 'cancelled': 1, 'success': 15}; push runs: 4 x ('2026-11-18', 'dev', 'failure'), 1 x 'cancelled'
  TinkerRocket sim-tests.yml: total=890 n=30 span=2026-11-12..2026-11-16 events={'pull_request': 20, 'push': 10} conclusions={'success': 27, 'failure': 3}

### L1-M2

PR open-to-merge minutes from saved PR JSON. Command: `python -I scripts/measure.py`. Sampling: the PRs read for content (not random), 7 biped. Output: biped 179 1.0, 197 67.8, 252 1.3, 290 2.0, 302 1.3, 312 33.2, 322 1.7, all author=hermes-tmw.

### L1-M3

Tree counts from the recursive git tree (1 call per repo, truncated=False). Command: `python -I scripts/measure.py`. Output: tomwhipple__biped-robot__tree: blobs=1565 hw_sessions_files=0.

### L1-M4

Branch rulesets. Command: `python -I scripts/rules.py <repo>:<branch>`, 1 call each, run 2026-11-19. Output: ARK32@main: 2 rules, deletion, non_fast_forward; TinkerRocket@main: 0 rules; SEAME@dev: 5 rules, incl. pull_request approvals 1, required_status_checks: []; openamr-platform-sw@main: 4 rules, required_status_checks: ['DCO', 'license/cla']; biped@main: 2 rules, deletion, non_fast_forward.

<!-- ledger Q2 -->
### L2-M1

`python -I scripts/count_footer.py` over data/prs2 (fetch_prs2.py, one GraphQL call per repo: merged PRs `first:N orderBy UPDATED_AT desc`, sorted by mergedAt; N=40 for biped, ARK32, TinkerRocket, SEAME; 30 for openamr-sw and -fw, of which fw returned 10). Output, trimmed: `tomwhipple__biped-robot: 40/40 bodies with agent footer; authors={'hermes-tmw': 40}; mergedBy={'hermes-tmw': 38, 'tomwhipple': 2}` / `Tinkerbug-Robotics__TinkerRocket: 40/40 ...; mergedBy={'tinkerbug': 40}` / `ARK-Electronics__ARK32: 21/40 ...; mergedBy={'AlexKlimaj': 33, 'dakejahl': 7}` / `openamr-platform-sw: 10/30 ...; mergedBy={'BotshareAI': 23, 'wikki26': 1, 'skunal3318': 6}` / `openamr-platform-fw: 2/10 ...; mergedBy={'BotshareAI': 10}`.

### L2-M2

`python -I scripts/classify.py`. Control paths: biped firmware/main, firmware/components, experiments/stepper; ARK32 Src, Inc, Mcu except SITL; TinkerRocket tinkerrocket-idf projects and components; SEAME drone/firmware, drone/lib, flight_interface, drone/config; openAMR sw ros2/src, fw boards, src, lib, firmware. Output: `biped sample=40 (2026-11-10..11-18) ctrl=13`; `ARK32 40 (08-24..11-18) ctrl=25`; `TinkerRocket 40 (10-25..11-16) ctrl=23`; `SEAME 40 (11-04..11-18) ctrl=21`; `openamr-sw 30 (10-08..11-15) ctrl=27`; `openamr-fw 10 (07-09..11-16) ctrl=3`.

### L2-M3

Hand classification of the 13 biped control PRs, from the body and pre-merge comments (`show_body.py`). Hardware evidence: #323, 292, 289, 302, 301, 254. Explicitly not run: #312, 287, 283, 298. Silent or host only: #300, 299, 328.

### L2-M4

Hand classification of the 25 ARK32 control PRs (`evidence_dump.py ARK-Electronics__ARK32`, body plus comments before and after merge). Bench before merge 11, after merge only 3, none 11. Merged 2026-11-06..11-18: 11/3/3 of 17. Merged 2026-08-24..09-23: 0/0/8.

### L2-M5

Hand classification of the 23 TinkerRocket control PRs (`evidence_dump.py`). Bench or RF-rig run 10, replay only 4, explicitly not benched or flown 7 (e.g. #1690, #1692), silent 2.

### L2-M6

`python -I scripts/seame_boxes.py`: `sample=40 merged PRs, mergedAt 2026-11-04..2026-11-18` / `Simulation: checked=4` / `Hardware: checked=9 [160, 169, 173, 177, 180, 183, 191, 192, 210]` / `Flight: checked=0 [] unchecked=38 absent=2`. Hand classification of the 21 control PRs: 8 with evidence (5 drone bench with props off, 3 HIL rig), 13 unticked with a stated reason.

### L2-M7

`python -I scripts/oamr_tally.py`: `openamr-platform-sw: sample=30` / `control PRs=27; body has not-verified/not-run wording=17` / `physical-run wording (body or pre-merge comments)=0 []` / `openamr-platform-fw: ... control PRs=3; ...=2 [14, 33]` / `physical-run wording=0 []`. Checked by reading the evidence_dump output for both repos.

### L2-M8

`gh_get.py ark_hwci_runs "repos/ARK-Electronics/ARK32/actions/workflows/hwci.yml/runs?per_page=30"` returned `{"total_count":0,"workflow_runs":[]}`. `gh_get.py ark_sitlcal_runs ".../SITL-calibration.yml/runs?per_page=20"` plus `runs_summary.py` returned `total_count 341 sampled 20 window 2026-11-11T21:47 .. 2026-11-18T20:26`, all `success`. `gh_get.py seame_hil_runs ".../hil.yaml/runs?per_page=40"` returned `total_count 277 sampled 40 window 2026-11-17T13:58 .. 2026-11-18T12:36` / `('workflow_dispatch', 'success'): 18, ('workflow_dispatch', 'failure'): 17, ('push', 'failure'): 4, ('push', 'cancelled'): 1`; the top branches are 8 bugfix/194-* branches. Each is one page of the newest runs.

### L2-M9

`gh_get.py biped_254_comments repos/tomwhipple/biped-robot/issues/254/comments` returned `--- hermes-tmw 2026-11-11T16:43:07Z`. The PR record shows `merged 2026-11-11T16:43:22Z by hermes-tmw`, 15 s later, and lists no reviews.

### L2-M10

`gh_search.py "repo:SEAME-pt/SEA-ME_Team1_ROSRangers flight in:title" 8` returned `total_count=12` / `issue #201 open 2026-11-16 Dot99: First MSP Override flight in the cage: mask 8 (yaw), then mask 11` / `issue #134 open 2026-10-30 ThiagoTEP: ANGLE hover and ALTHOLD in the lab flight area`. One call, best match first.

<!-- ledger Q3 -->
### L3-M1

GitHub issue-search totals, 2026-11-19, via `python scripts/search.py <out> '<query>'` (gh api search/issues, per_page 30, one call each). The first 30 results were scanned by title and keyword context; precision was not measured. `repo:tomwhipple/biped-robot "forgiving"` → `TOTAL: 3`; `repo:tomwhipple/biped-robot "not reproduced" OR "does not reproduce" OR "not reproduce"` → `TOTAL: 19`; `repo:PX4/PX4-Autopilot is:issue "works in SITL"` → `TOTAL: 36`; `repo:ArduPilot/ardupilot is:issue "works in SITL"` → `TOTAL: 25`. These are search hits, not gap counts; C352–C354 come from reading.

<!-- ledger Q4 -->
### L4-M1

Window: all PRs merged 2026-10-20..2026-11-19 (30 days), fetched in full by GraphQL search `repo:<r> is:pr is:merged merged:<window>` (scripts\fetch_prs.py: body, comments, reviews, files≤100, commits≤60), then filtered by control/estimation path regex (scripts\classify.py). PX4: src/modules/{ekf2, *_att_control, *_rate_control, mc_pos_control, fw_*, flight_mode_manager, control_allocator, vtol_att_control, rover_*, ...}, src/lib/{rate_control, pid, npfg, tecs, mathlib, ...}. ArduPilot: libraries/{AP_NavEKF*, AP_AHRS, AP_DAL, AC_AttitudeControl, AC_PosControl, AC_PID, AC_WPNav, APM_Control, AP_TECS, AR_*, AP_Motors, AP_Math, ...}. Output: `saved 367 calls 8`, `saved 167 calls 6`; `ctrl_prs: 51` (PX4), `ctrl_prs: 22` (ArduPilot). Regex pass PX4 `log_any: 7`: 4 logs.px4.io links from SIH/Gazebo runs (#29609, #29608, #29567, #29029), 2 bot link-check lists, 1 gist. Regex was noisy, so M2/M3 are hand-coded from scripts\digest.py and show.py output.

### L4-M2

PX4, 51 PRs, hand-coded. Real-vehicle 4: #29640 ("Test drive." on a mecanum rover), #29578 (real-log replay), #29525 ("above screenshots are from real flights"; fix verified in sim), #28798 (ground test, 2 GPS). Bench/board 5: #29842 ("Benchtested"), #29296, #29295, #29260, #29242 (MIMXRT1170-EVKB). Sim/unit/replay 31. None stated 11: #29827, #29819, #29797, #29626, #29518, #29495, #29483, #29472, #29237, #29200, #29010. Explicit not flown/not on hardware 3: #29660, #29641, #29534. Real-flight log linked 0.

### L4-M3

ArduPilot, 22 PRs. Raw checkbox counts: `box_tested_hardware: 3`, `box_logs_attached: 0`, `box_logs_request: 7`, `box_tested_manually: 16`, `box_automated_changes: 14`, `box_checked_programmer: 19`. Hardware/flight 5: #35173, #34584, #34208 (box), #34583 ("I flew this today using the fast rate rate loop without issue."), #34564 ("Flew this on the Hummer (tailsitter), 7" quad and a Bixler today."). Sim/autotest/unit/replay 12. Build-only/none 5: #35102, #35078, #31896, #35002, #28933. Explicit no-hardware 2: #35209, #35120. Logs linked 0.

### L4-M4

classify.py PX4 `ai_commit: 40` (of 51); ArduPilot body disclosure hand-coded 13 of 22. scripts\search1.py, last 100 default-branch commits (REST, per_page=100, 2026-11-19): `PX4 main last 100 commits; with Assisted-by: 47 ; with Co-authored-by: 28`; `AP master last 100 commits; with Assisted-by: 0 ; with Co-authored-by AI: 21 ; mentioning AI/Claude/Codex: 21`.

### L4-M5

ArduPilot, same 167-PR window. authors.py: `('github-actions', 145), ('AP-Review', 139)`; labels.py: `('AIReview', 116)`, `('MergeOnCIPass', 17)`; notexercised.py: `merged PRs: 167; with AP-Review comment: 139; with a 'Not exercised:' clause: 4; clause names flight/hardware/board: 3`.

### L4-M6

Workflow lists (gh api contents .github/workflows). PX4 has sitl_tests, failsafe_sim, ros_integration_tests, pr-ai-review, fuzzing; no sitl_tests_sih or mavros workflows (the scout listed them). ArduPilot has test_sitl_{blimp,copter,last_letter,periph,plane,rover,sub,tracker}, test_replay, test_renode; no test_sitl_godot.


## Open questions

- Q1 — whether ARK32's calibration gate ran on #128's first, bench-failing revision; the run history for that PR's head would settle it.
- Q1, Q3 — whether TinkerRocket's sim covered the tilt latch before the November flights; the sim tests at the flown commit would settle it.
- Q2 — whether `BotshareAI` is an agent or a maintainer working with agents; a maintainer's statement would settle it.
- Q2 — whether openAMRobot's evidence checker enforces anything; it was not found at the guessed path.
- Q2, Q4 — the hand-coded evidence classes were coded once; a second reader would settle how stable they are.
- Q3 — biped-robot's raw hardware sessions, ARK32's hardware-CI history and TinkerRocket's flight logs were not read.
- Q4 — whether px4bench actually runs at each PX4 release, and what ArduPilot's beta reports show; the release reports would settle it.
- Q4 — any PX4 or ArduPilot case of a CI-passed change failing in flight with a twin refit; a longer issue search would settle it.
- Q2 — whether ARK32, TinkerRocket and SEAME count a twin pass as acceptance in practice: no written statement either way was cited; their merge records set against twin results would settle it.
- Q2 — whether ARK32 and TinkerRocket keep any written rule on hardware stages outside ARK32's agent rules file; reading their CONTRIBUTING and docs would settle it.
- Q2, Q3 — biped-robot PR #192 said not to merge until checked on the bench, yet merged 12 s after a bot review; whether a bench check happened first is not in the report, and the PR's comments and hw_sessions notes would settle it.
- Q3 — whether ARK32 main's SITL calibration run was green while the #145 latch bug was on it; the calibration run on that main commit would settle it.
- Q4 — whether the ArduPilot rate-thread PR closed after a maintainer asked for flight data was AI-assisted; its commits or the author's statement would settle it.

## Sources

- [S1] https://github.com/tomwhipple/biped-robot/blob/main/sim/sil/README.md — passage
- [S2] https://github.com/tomwhipple/biped-robot/blob/main/docs/sil-harness.md — passage
- [S3] https://github.com/tomwhipple/biped-robot/blob/main/README.md — passage
- [S4] https://github.com/tomwhipple/biped-robot/blob/main/.github/workflows/ci.yml — passage
- [S5] https://github.com/tomwhipple/biped-robot/blob/main/AGENTS.md — passage
- [S6] https://github.com/tomwhipple/biped-robot/pull/179 — passage
- [S7] https://github.com/tomwhipple/biped-robot/blob/main/infra/night/planner_prompt.md — passage
- [S8] https://github.com/tomwhipple/biped-robot/issues/259 — passage
- [S9] https://github.com/tomwhipple/biped-robot/pull/252 — passage
- [S10] https://github.com/tomwhipple/biped-robot/pull/302 — passage
- [S11] https://github.com/tomwhipple/biped-robot/pull/322 — passage
- [S12] https://api.github.com/users/hermes-tmw — passage
- [S13] https://github.com/ARK-Electronics/ARK32/blob/main/Mcu/SITL/README.md — passage
- [S14] https://github.com/ARK-Electronics/ARK32/blob/main/.github/workflows/SITL-calibration.yml — passage
- [S15] https://github.com/ARK-Electronics/ARK32/blob/main/Mcu/SITL/data/ARK_4IN1_F051_900kv_noprop/README.md — passage
- [S16] https://github.com/ARK-Electronics/ARK32/blob/main/Mcu/SITL/run_calibration_tests.py — passage
- [S17] https://github.com/ARK-Electronics/ARK32/blob/main/Mcu/SITL/data/ARK_4IN1_F051_900kv_noprop/expected.json — passage
- [S18] https://github.com/ARK-Electronics/ARK32/blob/main/.github/workflows/hwci.yml — passage
- [S19] https://github.com/ARK-Electronics/ARK32/blob/main/hwci/README.md — passage
- [S20] https://github.com/ARK-Electronics/ARK32/pull/68 — passage
- [S21] https://github.com/ARK-Electronics/ARK32/pull/128 — passage
- [S22] https://github.com/ARK-Electronics/ARK32/blob/main/Mcu/SITL/TIMING-DESIGN.md — passage
- [S23] https://github.com/ARK-Electronics/ARK32/pull/135 — passage
- [S24] https://github.com/ARK-Electronics/ARK32/pull/145 — passage
- [S25] https://github.com/Tinkerbug-Robotics/TinkerRocket/blob/main/README.md — passage
- [S26] https://github.com/Tinkerbug-Robotics/TinkerRocket/blob/main/.github/workflows/hardware.yml — passage
- [S27] https://github.com/Tinkerbug-Robotics/TinkerRocket/blob/main/tools/rig_replay/README.md — passage
- [S28] https://github.com/Tinkerbug-Robotics/TinkerRocket/blob/main/docs/plans/1600-rig-mode.md — passage
- [S29] https://github.com/Tinkerbug-Robotics/TinkerRocket/blob/main/tinkerrocket-sim/scripts/fit_roll_flight.py — passage
- [S30] https://github.com/Tinkerbug-Robotics/TinkerRocket/pull/1423 — passage
- [S31] https://github.com/Tinkerbug-Robotics/TinkerRocket/pull/1690 — passage
- [S32] https://github.com/Tinkerbug-Robotics/TinkerRocket/pull/1703 — passage
- [S33] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/blob/dev/docs/PraticalPlan/02%20Decisions/ADR-019%20Sim%20Backends.md — passage
- [S34] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/pull/190 — passage
- [S35] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/blob/dev/docs/PraticalPlan/04%20CI-CD/HIL%20Overview.md — passage
- [S36] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/blob/dev/.github/workflows/hil.yaml — passage
- [S37] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/blob/dev/drone/config/betaflight/info.md — passage
- [S38] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/pull/144 — passage
- [S39] https://github.com/openAMRobot/openamr-platform-sw/blob/main/.github/workflows/sil-tests.yml — passage
- [S40] https://github.com/openAMRobot/openamr-platform-sw/blob/main/AGENTS.md — passage
- [S41] https://github.com/openAMRobot/openamr-platform-sw/blob/main/simulation/README.md — passage
- [S42] https://github.com/openAMRobot/openamr-platform-sw/pull/161 — passage
- [S43] https://github.com/openAMRobot/openamr-upperbody-sw/pull/67 — passage
- [S44] https://raw.githubusercontent.com/tomwhipple/biped-robot/HEAD/AGENTS.md — passage
- [S45] https://raw.githubusercontent.com/tomwhipple/biped-robot/HEAD/infra/night/planner_prompt.md — passage
- [S46] https://raw.githubusercontent.com/tomwhipple/biped-robot/HEAD/experiments/stepper/2026-11-11-robot/README.md — passage
- [S47] https://github.com/tomwhipple/biped-robot/pull/254 — passage
- [S48] https://github.com/tomwhipple/biped-robot/pull/254#issuecomment-6801649307 — passage
- [S49] https://github.com/tomwhipple/biped-robot/pull/300 — passage
- [S50] https://raw.githubusercontent.com/ARK-Electronics/ARK32/HEAD/.github/workflows/hwci.yml — passage
- [S51] https://raw.githubusercontent.com/ARK-Electronics/ARK32/HEAD/.github/workflows/SITL-calibration.yml — passage
- [S52] https://raw.githubusercontent.com/ARK-Electronics/ARK32/HEAD/AGENTS.md — passage
- [S53] https://github.com/ARK-Electronics/ARK32/pull/130 — passage
- [S54] https://github.com/ARK-Electronics/ARK32/pull/122#issuecomment-6777811166 — passage
- [S55] https://github.com/Tinkerbug-Robotics/TinkerRocket/pull/1695 — passage
- [S56] https://github.com/Tinkerbug-Robotics/TinkerRocket/pull/1705 — passage
- [S57] https://raw.githubusercontent.com/SEAME-pt/SEA-ME_Team1_ROSRangers/dev/.github/pull_request_template.md — passage
- [S58] https://raw.githubusercontent.com/SEAME-pt/SEA-ME_Team1_ROSRangers/dev/docs/PraticalPlan/05%20Hardware/Safety%20Rules.md — passage
- [S59] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/pull/177 — passage
- [S60] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/pull/197 — passage
- [S61] https://raw.githubusercontent.com/openAMRobot/openamr-platform-sw/HEAD/AGENTS.md — passage
- [S62] https://github.com/openAMRobot/openamr-platform-sw/pull/139 — passage
- [S63] https://github.com/openAMRobot/openamr-platform-sw/pull/93 — passage
- [S64] https://github.com/openAMRobot/openamr-platform-sw/pull/126 — passage
- [S65] https://github.com/tomwhipple/biped-robot/issues/29 — passage
- [S66] https://github.com/tomwhipple/biped-robot/pull/192 — passage
- [S67] https://github.com/tomwhipple/biped-robot/pull/158 — passage
- [S68] https://github.com/tomwhipple/biped-robot/pull/215 — passage
- [S69] https://github.com/tomwhipple/biped-robot/blob/main/experiments/stepper/2026-11-11-robot/README.md — passage
- [S70] https://github.com/tomwhipple/biped-robot/pull/290 — passage
- [S71] https://github.com/tomwhipple/biped-robot/pull/324 — passage
- [S72] https://github.com/ARK-Electronics/ARK32/pull/137 — passage
- [S73] https://github.com/ARK-Electronics/ARK32/pull/123 — passage
- [S74] https://github.com/ARK-Electronics/ARK32/pull/111 — passage
- [S75] https://github.com/Tinkerbug-Robotics/TinkerRocket/pull/1704 — passage
- [S76] https://github.com/Tinkerbug-Robotics/TinkerRocket/issues/1281 — passage
- [S77] https://github.com/Tinkerbug-Robotics/TinkerRocket/pull/1377 — passage
- [S78] https://github.com/Tinkerbug-Robotics/TinkerRocket/pull/1522 — passage
- [S79] https://github.com/Tinkerbug-Robotics/TinkerRocket/pull/1581 — passage
- [S80] https://github.com/Tinkerbug-Robotics/TinkerRocket/issues/1211 — passage
- [S81] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/pull/191 — passage
- [S82] https://github.com/SEAME-pt/SEA-ME_Team1_ROSRangers/issues/61 — passage
- [S83] https://github.com/mowglinext/mowglinext/pull/539 — passage
- [S84] https://github.com/mowglinext/mowglinext/issues/1142 — passage
- [S85] https://github.com/PX4/PX4-Autopilot/issues/27497 — passage
- [S86] https://github.com/PX4/PX4-Autopilot/issues/16586 — passage
- [S87] https://github.com/PX4/PX4-Autopilot/commit/ced91f135be930011b41c7f4a71cf3454d97b7b4 — passage
- [S88] https://github.com/ArduPilot/ardupilot/issues/6594 — passage
- [S89] https://github.com/ArduPilot/ardupilot/issues/17416 — passage
- [S90] https://github.com/ArduPilot/ardupilot/issues/21382 — passage
- [S91] https://github.com/PX4/PX4-Autopilot/blob/main/.github/workflows/sitl_tests.yml — passage
- [S92] https://github.com/PX4/PX4-Autopilot/blob/main/docs/en/test_and_ci/integration_testing.md — passage
- [S93] https://github.com/PX4/PX4-Autopilot/blob/main/docs/en/sim_sih/index.md — passage
- [S94] https://github.com/PX4/PX4-Autopilot/blob/main/docs/en/simulation/hitl.md — passage
- [S95] https://github.com/PX4/PX4-Autopilot/blob/main/docs/en/test_and_ci/bench_testing.md — passage
- [S96] https://github.com/PX4/PX4-Autopilot/blob/main/docs/en/test_and_ci/test_flights.md — passage
- [S97] https://github.com/PX4/PX4-Autopilot/pull/29712 — passage
- [S98] https://github.com/PX4/PX4-Autopilot/blob/main/CONTRIBUTING.md — passage
- [S99] https://github.com/PX4/PX4-Autopilot/blob/main/docs/en/contribute/code.md — passage
- [S100] https://github.com/PX4/PX4-Autopilot/blob/main/docs/en/contribute/ai_assistants.md — passage
- [S101] https://github.com/PX4/PX4-Autopilot/blob/main/.agents/skills/pr/SKILL.md — passage
- [S102] https://github.com/PX4/PX4-Autopilot/blob/main/docs/en/test_and_ci/ai_review.md — passage
- [S103] https://github.com/ArduPilot/ardupilot/blob/master/AGENTS.md — passage
- [S104] https://ardupilot.org/dev/docs/testing-with-replay.html — passage
- [S105] https://github.com/ArduPilot/ardupilot/blob/master/.github/workflows/test_renode.yml — passage
- [S106] https://ardupilot.org/dev/docs/hitl-simulators.html — passage
- [S107] https://ardupilot.org/dev/docs/release-procedures.html — passage
- [S108] https://github.com/ArduPilot/ardupilot/blob/master/.github/PULL_REQUEST_TEMPLATE.md — passage
- [S109] https://ardupilot.org/dev/docs/submitting-patches-back-to-master.html — passage
- [S110] https://github.com/ArduPilot/ardupilot/pull/32841 — passage
- [S111] https://github.com/ArduPilot/ardupilot/pull/35050 — passage
- [S112] https://github.com/PX4/PX4-Autopilot/pull/28674 — passage
- [S113] https://github.com/ArduPilot/ardupilot/pull/34208 — passage
- [S114] https://github.com/PX4/PX4-Autopilot/pull/29578 — passage
- [S115] https://github.com/ArduPilot/ardupilot/pull/35173 — passage
- [S116] https://github.com/PX4/PX4-Autopilot/pull/28798 — passage

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED |  |
| C102 | SUPPORTED |  |
| C103 | SUPPORTED |  |
| C104 | SUPPORTED |  |
| C105 | SUPPORTED |  |
| C106 | SUPPORTED |  |
| C107 | SUPPORTED |  |
| C108 | SUPPORTED |  |
| C110 | SUPPORTED |  |
| C112 | SUPPORTED |  |
| C113 | SUPPORTED |  |
| C114 | SUPPORTED |  |
| C115 | SUPPORTED |  |
| C116 | SUPPORTED |  |
| C117 | SUPPORTED |  |
| C118 | SUPPORTED |  |
| C119 | SUPPORTED |  |
| C120 | SUPPORTED |  |
| C121 | SUPPORTED |  |
| C122 | SUPPORTED |  |
| C123 | SUPPORTED |  |
| C125 | SUPPORTED |  |
| C126 | SUPPORTED |  |
| C127 | SUPPORTED |  |
| C128 | SUPPORTED |  |
| C129 | SUPPORTED |  |
| C130 | SUPPORTED |  |
| C131 | SUPPORTED |  |
| C132 | PARTIAL | source does not show the bench-failing revision passed SITL; calibration passed "on an earlier revision"; narrowed |
| C133 | SUPPORTED |  |
| C135 | SUPPORTED |  |
| C136 | SUPPORTED |  |
| C137 | PARTIAL | "not in SITL" not in the quote; dropped |
| C138 | SUPPORTED |  |
| C139 | SUPPORTED |  |
| C141 | SUPPORTED |  |
| C142 | SUPPORTED |  |
| C143 | SUPPORTED |  |
| C144 | SUPPORTED |  |
| C145 | SUPPORTED |  |
| C146 | SUPPORTED |  |
| C147 | SUPPORTED |  |
| C148 | SUPPORTED |  |
| C149 | SUPPORTED |  |
| C151 | SUPPORTED | quote found in the PR text read via the GitHub API; the plain HTML fetch misses it (PR body) |
| C153 | PARTIAL | event types are known only for the 30 sampled runs; narrowed |
| C154 | SUPPORTED |  |
| C155 | SUPPORTED |  |
| C156 | SUPPORTED |  |
| C157 | SUPPORTED |  |
| C158 | SUPPORTED |  |
| C159 | SUPPORTED |  |
| C160 | SUPPORTED |  |
| C161 | SUPPORTED |  |
| C163 | PARTIAL | L1-M1 shows 4 dev push failures and 1 cancelled run on an unshown branch; narrowed |
| C164 | SUPPORTED |  |
| C165 | SUPPORTED |  |
| C166 | SUPPORTED |  |
| C167 | SUPPORTED |  |
| C168 | SUPPORTED |  |
| C169 | SUPPORTED |  |
| C170 | SUPPORTED |  |
| C172 | SUPPORTED |  |
| C173 | PARTIAL | "only ARK32" not established: TinkerRocket's test_scenario_e also checks the twin against a flight; narrowed |
| C174 | PARTIAL | the named premises cover ARK32, SEAME, biped only; narrowed to the rigs found |
| C175 | PARTIAL | "most twin code" unmeasured; C146 says nothing about authorship; TinkerRocket dropped |
| C176 | PARTIAL | "refits lag hardware failures" is an extra premise; narrowed to what C113, C117, C118, C115 say |
| C177 | PARTIAL | "most common" not measured against refit; narrowed to a list |
| C178 | PARTIAL | rests on narrowed C132 and C137; whether SITL passed the failing code is unconfirmed |
| C201 | SUPPORTED |  |
| C207 | SUPPORTED |  |
| C208 | SUPPORTED |  |
| C209 | SUPPORTED |  |
| C211 | SUPPORTED |  |
| C212 | SUPPORTED |  |
| C213 | SUPPORTED |  |
| C214 | SUPPORTED |  |
| C215 | SUPPORTED |  |
| C216 | SUPPORTED |  |
| C217 | SUPPORTED |  |
| C218 | SUPPORTED |  |
| C219 | SUPPORTED |  |
| C220 | SUPPORTED |  |
| C221 | SUPPORTED |  |
| C223 | SUPPORTED |  |
| C224 | SUPPORTED |  |
| C225 | SUPPORTED |  |
| C226 | SUPPORTED |  |
| C227 | SUPPORTED |  |
| C229 | SUPPORTED |  |
| C230 | SUPPORTED |  |
| C231 | PARTIAL | "no written rule" checked only in the agent rules file; "thrust stand" not shown for PR benches; narrowed |
| C232 | SUPPORTED |  |
| C235 | SUPPORTED |  |
| C236 | SUPPORTED |  |
| C237 | SUPPORTED |  |
| C238 | SUPPORTED |  |
| C239 | SUPPORTED |  |
| C240 | PARTIAL | no claim establishes the absence of a rules file or who the owner is; narrowed |
| C241 | SUPPORTED |  |
| C242 | SUPPORTED |  |
| C243 | SUPPORTED |  |
| C245 | SUPPORTED |  |
| C246 | SUPPORTED |  |
| C249 | SUPPORTED |  |
| C250 | SUPPORTED |  |
| C251 | SUPPORTED |  |
| C252 | PARTIAL | one PR (#197), not "some"; quote found in the PR text read via the GitHub API; the plain HTML fetch misses it (PR comment) |
| C253 | PARTIAL | "mostly" not in L2-M8; restated as recorded |
| C254 | PARTIAL | "first hover" not in #134's title; restated as recorded |
| C255 | PARTIAL | SITL in CI is Betaflight, not PX4; the HIL rig may run unattended; "never by the agent" not shown; narrowed |
| C256 | SUPPORTED |  |
| C257 | SUPPORTED |  |
| C258 | SUPPORTED |  |
| C261 | SUPPORTED |  |
| C264 | SUPPORTED |  |
| C265 | SUPPORTED |  |
| C266 | SUPPORTED |  |
| C267 | SUPPORTED |  |
| C269 | PARTIAL | "never merge not visible in practice" depends on BotshareAI being an agent, which is unsettled; narrowed |
| C270 | PARTIAL | "no project" is unshown for ARK32, TinkerRocket, SEAME; TinkerRocket twin coverage before #1690 is unknown (Disconfirming); narrowed to biped |
| C271 | PARTIAL | "never machine-checked" not shown (openAMR's checker unverified, hwci CLI exits non-zero); narrowed |
| C272 | PARTIAL | TinkerRocket "none" rests on no claim; "only" dropped |
| C301 | SUPPORTED |  |
| C302 | SUPPORTED |  |
| C303 | SUPPORTED |  |
| C304 | PARTIAL | PR #192 merged 2026-11-02T00:28:28Z by hermes-tmw, 12 s after a bot review; "merge held" is false; dropped |
| C305 | SUPPORTED |  |
| C306 | SUPPORTED |  |
| C307 | SUPPORTED |  |
| C308 | SUPPORTED |  |
| C309 | SUPPORTED |  |
| C310 | SUPPORTED |  |
| C311 | SUPPORTED |  |
| C312 | SUPPORTED |  |
| C313 | SUPPORTED |  |
| C314 | SUPPORTED |  |
| C315 | SUPPORTED |  |
| C316 | SUPPORTED |  |
| C317 | SUPPORTED |  |
| C318 | SUPPORTED |  |
| C319 | SUPPORTED |  |
| C320 | SUPPORTED |  |
| C321 | SUPPORTED |  |
| C322 | PARTIAL | "had passed SITL CI" not in S24; dropped |
| C323 | PARTIAL | the quoted test fails on main; the other two fail on a26835eb and without the DroneCAN change; restated |
| C324 | SUPPORTED |  |
| C325 | SUPPORTED |  |
| C326 | SUPPORTED | quote found in the PR text read via the GitHub API; the plain HTML fetch misses it (PR body) |
| C327 | SUPPORTED |  |
| C328 | SUPPORTED |  |
| C329 | SUPPORTED |  |
| C330 | SUPPORTED |  |
| C331 | SUPPORTED |  |
| C332 | SUPPORTED |  |
| C333 | SUPPORTED |  |
| C334 | SUPPORTED |  |
| C335 | SUPPORTED |  |
| C336 | SUPPORTED |  |
| C337 | SUPPORTED |  |
| C338 | SUPPORTED |  |
| C339 | SUPPORTED |  |
| C340 | SUPPORTED | quote found in the PR text read via the GitHub API; the plain HTML fetch misses it (PR body checklist) |
| C341 | SUPPORTED |  |
| C342 | SUPPORTED |  |
| C343 | SUPPORTED |  |
| C344 | SUPPORTED |  |
| C345 | SUPPORTED |  |
| C346 | SUPPORTED |  |
| C347 | SUPPORTED |  |
| C348 | SUPPORTED |  |
| C349 | SUPPORTED |  |
| C350 | SUPPORTED |  |
| C351 | SUPPORTED |  |
| C352 | PARTIAL | the listed records are 8, not 9 (#310/#322 joined); #302 counted twice; recounted |
| C353 | PARTIAL | only #137's and one #145 test are said to fail on main; #128's test is not; #123 is an open proposal, not a fix; narrowed |
| C354 | SUPPORTED |  |
| C355 | PARTIAL | biped 3 and TinkerRocket 2 gaps got no twin change; comparator side rests on one case each; narrowed |
| C356 | SUPPORTED |  |
| C401 | SUPPORTED |  |
| C402 | SUPPORTED |  |
| C403 | SUPPORTED |  |
| C404 | SUPPORTED | quote's bracketed text is a markdown link in S94; found by reading |
| C405 | SUPPORTED |  |
| C406 | SUPPORTED |  |
| C407 | PARTIAL | S95 does not call it an option or say it is not running; restated as the doc says |
| C408 | SUPPORTED |  |
| C409 | PARTIAL | the comment says the team is testing 1.18 and the maintainer is unsure; "holds late merges" goes further |
| C410 | SUPPORTED |  |
| C411 | SUPPORTED |  |
| C412 | SUPPORTED |  |
| C413 | PARTIAL | the PR-template part has no quote or source; dropped |
| C414 | SUPPORTED |  |
| C415 | SUPPORTED |  |
| C416 | SUPPORTED |  |
| C417 | SUPPORTED |  |
| C418 | SUPPORTED |  |
| C419 | SUPPORTED |  |
| C420 | SUPPORTED |  |
| C421 | SUPPORTED |  |
| C422 | SUPPORTED |  |
| C423 | SUPPORTED |  |
| C424 | SUPPORTED |  |
| C425 | SUPPORTED |  |
| C426 | SUPPORTED |  |
| C427 | SUPPORTED |  |
| C428 | SUPPORTED |  |
| C429 | SUPPORTED |  |
| C430 | PARTIAL | AI assistance of the PR is not established; the maintainer conditions on the analysis being AI-only; restated |
| C431 | SUPPORTED |  |
| C432 | SUPPORTED |  |
| C433 | SUPPORTED |  |
| C434 | SUPPORTED |  |
| C435 | SUPPORTED |  |
| C436 | SUPPORTED |  |
| C437 | SUPPORTED |  |
| C438 | SUPPORTED |  |
| C439 | PARTIAL | "9 PRs with real-vehicle evidence, 4 AI-assisted" is not in the recorded output; dropped |
| C440 | SUPPORTED |  |
| C441 | SUPPORTED |  |
| C442 | SUPPORTED |  |
| C443 | SUPPORTED | quote found in the PR text read via the GitHub API; the plain HTML fetch misses it (comment by dakejahl, written by Claude on his behalf) |
| C444 | PARTIAL | C412 shows PX4 asks for flight logs; "mainly at release" not measured; narrowed |
| C445 | PARTIAL | "same bar" is stated by PX4 only; narrowed |

Label verdict: open — the Summary rests on single-reader evidence classes and on unsettled sub-questions (whether ARK32, TinkerRocket and SEAME treat a twin pass as acceptance; whether openAMRobot's merging account is an agent; biped #192's bench timing), any of which could change practices 1 and 4.

Quote check: Quote check hardware-twin-to-real-agent-projects-2026-11-19.md: 178 quoted claim(s): 170 found, 6 NOT FOUND, 2 unfetchable, 0 no source

## Disposition

| Recommendation | State | Where |
|---|---|---|
| Write the twin's prediction down before a real run, and the real numbers beside it after | deferred | unfiled: an input to the robotics discussion with Danya on 2026-11-20; no incident of ours behind it yet |
| Turn each hardware-found gap into a twin test that fails on the old code, or into a refit, and say in the PR what the twin still misses | deferred | unfiled: an input to the robotics discussion with Danya on 2026-11-20; no incident of ours behind it yet |
| Calibrate the plant against measured hardware data in CI | deferred | unfiled: an input to the robotics discussion with Danya on 2026-11-20; needs a recorded hardware dataset first |
| Keep agents off real-device stages by a written rule, and check who actually merges | deferred | unfiled: an input to the /grill on merge holds with Danya on 2026-11-20 |
