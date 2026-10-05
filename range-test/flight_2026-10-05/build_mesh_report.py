"""PDF report for the 2026-10-05 mesh range flight (from results_mesh.json and charts/m*.png)."""
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from PIL import Image as PI

R = json.load(open("results_mesh.json"))
F = json.load(open("results_fc.json"))
OUT = "MESH_RANGE_REPORT_2026-10-05.pdf"
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15, spaceAfter=6, textColor=colors.HexColor("#0d2b4e"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], keepWithNext=1, fontSize=12, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#0d2b4e"))
B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.3, leading=12.5, spaceAfter=4)
S = ParagraphStyle("S", parent=B, fontSize=8, leading=10.5, textColor=colors.HexColor("#444444"))
CELL = ParagraphStyle("C", parent=B, fontSize=8.4, leading=10.5, spaceAfter=0)
BUL = ParagraphStyle("BUL", parent=B, leftIndent=12, bulletIndent=2)
p = lambda t, st=B: Paragraph(t, st)
bl = lambda t: Paragraph(t, BUL, bulletText="-")


def img(path, w=7.0):
    iw, ih = PI.open(path).size
    return Image(path, width=w * inch, height=w * inch * ih / iw)


def table(rows, widths):
    t = Table([[Paragraph(str(c), CELL) for c in r] for r in rows], colWidths=[w * inch for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#bbbbbb")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe8f3")),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    return t


f1 = lambda v, d=1: "-" if v is None else f"{v:.{d}f}"
mmss = lambda s: f"{int(s // 60)}:{int(s % 60):02d}"
band = lambda lo: f"{lo} to {lo + 500} m"
bn = R["bins"]
PT = R["ping_totals"]

story = [p("3 km mesh range test: mesh link report", H1),
         p(f"Flight of {R['date_local']}, Clark Range / Fort McClellan airfield, Alabama. Source: the Pi's mesh logger (v2), read from the Pi's SD card after the flight, session of {mmss(R['log_len'])} (mm:ss). "
           "The drone's position comes from the flight telemetry the Pi forwarded to the phone, with the drone's own GPS clock, so times below are local (CDT) and exact. "
           "The flight controller's own log (log #18, read from its SD card) is used for the battery and failsafe findings in section 4. <b>The phone's QGC data and any video were not available</b>, so there is no video analysis. Section 7 lists what is missing.", B)]

story += [p("1. Test summary", H2)]
rows = [["Item", "Result"],
        ["Takeoff / far point / end of Pi log (local)", f"{R['takeoff_local']} / {R['far_local']} / {R['last_local']}"],
        ["Time from takeoff to the far point", f"{mmss(R['out_s'])} (cruise speed {R['cruise_speed']:.1f} m/s, peak {R['max_speed']:.1f} m/s)"],
        ["Maximum distance from home", f"{R['max_h']:.0f} m horizontal, {R['max_3d']:.0f} m in 3D"],
        ["Maximum altitude above home", f"{R['max_alt']:.1f} m ({R['max_alt'] * 3.281:.0f} ft)"],
        ["How the flight ended", f"<b>The battery ran out.</b> The low-battery failsafe fired at the far point ({F['v_low']:.2f} V) and started an RTL. The critical failsafe ({F['v_crit']:.2f} V) started a Land {F['dist_crit']:.0f} m from home at {F['alt_land_start']:.0f} m altitude. "
                                  f"The pack voltage then collapsed to {F['v_end']:.1f} V, and the flight controller's log ends at {F['end']['alt']:.0f} m altitude, {F['end']['dist']:.0f} m from home. The Pi lost power at the same time (section 4)."],
        ["Mesh link established at", f"{mmss(R['link_up_at'])} into the log, about {mmss(R['t_to'] - R['link_up_at'])} before takeoff (the radio is powered on after the Pi)"]]
story += [table(rows, [2.3, 4.7]), Spacer(1, 6),
          p(f"<b>In short:</b> the mesh link held to <b>{R['max_3d']:.0f} m</b> at about 220 m altitude. On the way out it was clean: no ping blackouts and the Pi never lost its login to the radios. "
            f"The drone-side radio still read {R['far_rssi_drone']:.0f} dBm at the far point with about {R['far_snr_drone']:.0f} dB of signal-to-noise. "
            "<b>The return leg was worse than the outbound leg</b>, with three 5 to 6 s blackouts between 1.5 and 2.2 km and an erratic signal at the ground radio. That is the main thing to explain (section 3). <b>The flight also ended because the battery ran out</b> (section 4): this 6.3 km round trip needed far more than the pack had.", B),
          img("charts/m01_flight_profile.png", 5.2),
          p("Figure 1. Distance, altitude and ground speed from the forwarded telemetry. The grey line is the far point; the red line is where the Pi lost power (the battery collapsed).", S)]

story += [p("2. Radio signal against distance", H2),
          p("There are two radios in the data: the <b>drone-side radio</b> (wired to the Pi on the aircraft) and the <b>ground radio RN03</b>, which the Pi read over the mesh. "
            "Each one reports how strongly it hears the other. All values are averages over each 500 m of 3D distance (horizontal distance and altitude combined).", B)]
rows = [["Distance band", "Drone radio signal (dBm)", "Drone radio SNR (dB)", "RN03 signal out / back (dBm)", "RN03 SNR (dB)", "Noise floor (dBm)"]]
for i, b in enumerate(bn["rad_rssi"]):
    rn_, sn_, rs_, nz_ = bn["rn_rssi"][i], bn["rad_snr"][i], bn["rn_snr"][i], bn["rad_noise"][i]
    rows.append([band(b["lo"]), f"{f1(b['mean'])} (worst {f1(b['mn'], 0)})", f1(sn_["mean"]), f"{f1(rn_['out'])} / {f1(rn_['ret'])}", f1(rs_["mean"]), f1(nz_["mean"])])
story += [table(rows, [1.05, 1.5, 1.0, 1.45, 0.9, 1.0]), Spacer(1, 4),
          img("charts/m02_rssi_snr_vs_distance.png", 6.6),
          p("Figure 2. Signal strength and SNR against 3D distance, outbound (blue) and return (orange).", S),
          bl(f"<b>Drone radio:</b> signal fell from about -59 dBm in the first 500 m to about -75 dBm by 2 km, then stayed flat out to the far point ({R['far_rssi_drone']:.0f} dBm). The lowest reading was {R['rssi_min_drone']:.0f} dBm. "
             f"SNR stayed above {R['snr_min_drone']:.0f} dB throughout and was about {R['far_snr_drone']:.0f} dB at the far point."),
          bl("<b>Noise floor:</b> flat at about -90 dBm from the first metre to the far point. No interference rise was seen on the 907 MHz band during this flight."),
          bl(f"<b>RN03 (ground):</b> about -54 dBm out to the far point and an SNR near 40 dB. It heard the drone <b>10 to 20 dB worse on the way back</b> (for example -66 dBm in the 500 to 1500 m bands, with deep dips) even at distances it had held steadily on the way out."),
          bl(f"<b>Trend:</b> the drone radio's signal fell about {abs(R['fit']['drone']['slope_per_decade']):.0f} dB for each tenfold increase in distance, slower than the 20 dB of free space. "
             "That is what a clear line of sight over the terrain, with a rising aircraft, would produce. It is a rough fit, not a precise model."),
          img("charts/m03_noise_bitrate_retries.png", 6.6),
          p("Figure 3. Noise floor, the bit rate the radio chose, transmit retries and the altitude profile.", S)]
rows = [["Distance band", "Drone radio bit rate (Mbit/s, median)", "RN03 bit rate (Mbit/s, median)"]]
for i, b in enumerate(R["bitrate"]["rad_tx"]):
    rows.append([band(b["lo"]), f1(b["med"]), f1(R["bitrate"]["rn_tx"][i]["med"])])
story += [table(rows, [1.5, 2.5, 2.5]), Spacer(1, 4),
          p("The drone radio's sending rate fell from 58.5 Mbit/s near launch to 19.5 Mbit/s beyond 1.5 km: the radio gave up speed for reliability as the signal weakened. "
            "RN03's sending rate stayed at 58.5 Mbit/s all the way, which is consistent with the ground radio having the stronger signal.", B),
          img("charts/m06_signal_vs_altitude.png", 6.4),
          p("Figure 4. Signal against altitude. Altitude and distance rise together on this route, so they can't be separated in this flight (a flat-altitude flight would be needed).", S)]

story += [p("3. Link quality over time: pings, dropouts and the return leg", H2),
          p("The Pi pinged the ground radio RN03 and the phone about once a second. A ping that reaches RN03 shows the mesh link is carrying traffic; a ping to the phone also crosses RN03's Wi-Fi.", B)]
rows = [["Distance band", "RN03 ping loss", "RN03 delay median / 95th / max (ms)", "Phone ping loss", "Phone delay median / 95th (ms)"]]
for i, lo in enumerate(range(0, 3500, 500)):
    a, c = R["ping_bins"]["rn03_ground"][i], R["ping_bins"]["phone"][i]
    rows.append([band(lo), f"{f1(a.get('loss'))}%", f"{f1(a.get('med'))} / {f1(a.get('p95'), 0)} / {f1(a.get('mx'), 0)}", f"{f1(c.get('loss'))}%", f"{f1(c.get('med'))} / {f1(c.get('p95'), 0)}"])
story += [table(rows, [1.2, 1.0, 1.9, 1.0, 1.9]), Spacer(1, 4),
          p(f"Over the whole flight after takeoff the Pi sent {PT['rn03_ground']['sent']} pings to RN03 and lost {PT['rn03_ground']['loss']:.1f}% (median delay {PT['rn03_ground']['med']:.1f} ms, 95th percentile {PT['rn03_ground']['p95']:.0f} ms, worst {PT['rn03_ground']['mx']:.0f} ms). "
            f"To the phone: {PT['phone']['loss']:.1f}% lost, median {PT['phone']['med']:.1f} ms. Pings to the Pi's own radio lost none. The loss and the long delays are concentrated on the return leg and in the far third of the outbound leg.", B),
          img("charts/m04_ping_loss_latency.png", 6.6),
          p("Figure 5. Ping loss and delay in 30 s windows against 3D distance (blue = outbound, orange = return).", S),
          img("charts/m05_timeline.png", 6.4),
          p("Figure 6. Timeline: distance, the two radios' signal, ping blackouts of 3 s or more, and QGC messages reaching the drone per 2 s. Grey lines are moments when the Pi lost its login to RN03.", S)]
rows = [["What", "When (local)", "Seconds after takeoff", "Distance", "Altitude", "Leg"]]
for n_, label in (("rn03_ground", "RN03 ping blackout"), ("phone", "Phone ping blackout")):
    for b in R["blackouts"][n_]:
        rows.append([f"{label}, {b['dur']:.0f} s", b["local"], f"{b['t_rel']:.0f}", f"{b['dist']:.0f} m", f"{b['alt']:.0f} m", "outbound" if b["out"] else "return"])
for x in R["ssh_down"]:
    rows.append(["Login to RN03 lost", x["local"], f"{x['t_rel']:.0f}", f"{x['dist']:.0f} m", f"{x['alt']:.0f} m", "return"])
story += [table(rows, [2.0, 0.9, 1.1, 0.9, 0.8, 0.8]), Spacer(1, 4),
          p("<b>What stands out</b>", B),
          bl("The outbound leg had <b>no blackouts at all</b>, out to 3.16 km."),
          bl("On the return leg, between about 2.2 km and 1.5 km, the link dropped three times for 5 to 6 s, QGC messages to the drone stopped arriving in several 2 s intervals, and the Pi lost its login to RN03 three times. "
             "The drone's own radio signal stayed near -75 dBm during this period, so the drone still heard the ground radio. What got worse was the <b>ground radio hearing the drone</b> (RN03 signal fell and became erratic)."),
          bl("<b>The return was not the outbound route.</b> The low-battery failsafe fired at the far point and switched the aircraft to RTL, so it flew a straight line home at the cruise speed instead of retracing the road. "
             "A weaker drone-to-ground path on the return also fits a change in the aircraft's antenna orientation: it was now flying facing the other way, so the antennas point differently relative to the ground radio, and the airframe or battery can shadow them. "
             "<b>This is a hypothesis; the data can't prove it.</b> Other possibilities are a local obstruction or interference near the 1.5 to 2.2 km point on the return track, or the aircraft's attitude changes."),
          bl("<b>GPS glitch reports line up with two of the three phone blackouts.</b> The flight controller logged \"GPS Glitch or Compass error\" at 450 s and 461 s after takeoff, within a few seconds of the first two blackouts (the clocks were matched to a few seconds). The third blackout (511 s) had no glitch, and three more glitches (539, 550 and 583 s) had no blackout. GPS quality stayed good (at least 10 satellites, HDOP at most 1.0) the whole time. Interference or a power-quality disturbance that hits both the GPS or compass and the radio is a possibility worth checking, but two matches is not proof.") ,
          bl("The telemetry the Pi sent toward the phone ran steady at about 92 messages per second for the whole flight, so the Pi's side of the telemetry never stalled. That figure counts what the Pi sent, not what the phone received."),
          bl("Pings to a third node (Josh's handheld) never answered, because that radio was not on the mesh. They are ignored here.")]

story += [p("4. Battery and the end of the flight (flight controller log #18)", H2),
          p("This section comes from the flight controller's own log, which was read from its SD card. Times are seconds after takeoff.", B)]
rows = [["Event", "Time", "Pack voltage", "Distance from home", "Altitude"],
        ["Takeoff, Auto mission begins", "0", f"{F['v_start']:.2f} V (resting before takeoff)", "0 m", "0 m"],
        ["Far point reached", f"{F['t_far'] - F['t_to']:.0f} s", f"{F['v_far']:.2f} V", f"{R['max_3d']:.0f} m", "220 m"],
        [f"<b>Low-battery failsafe (saved setting {F['params']['BATT_LOW_VOLT']:.1f} V):</b> the flight controller switches to RTL", f"{F['t_low_rel']:.0f} s", f"{F['v_low']:.2f} V", f"{F['dist_low']:.0f} m", "220 m"],
        [f"<b>Critical-battery failsafe (saved setting {F['params']['BATT_CRT_VOLT']:.1f} V):</b> the flight controller switches to Land", f"{F['t_crit_rel']:.0f} s", f"{F['v_crit']:.2f} V", f"{F['dist_land_start']:.0f} m", f"{F['alt_land_start']:.0f} m"],
        ["'Potential Thrust Loss' reported (motor 4)", f"{F['t_thrust_rel']:.0f} s", f"{F['v_thrust']:.1f} V", "", ""],
        ["Last record in the log", f"{F['t_end_rel']:.0f} s", f"{F['v_end']:.1f} V", f"{F['end']['dist']:.0f} m", f"{F['end']['alt']:.0f} m"]]
story += [table(rows, [3.0, 0.7, 1.4, 1.1, 0.8]), Spacer(1, 4), img("charts/m08_battery_failsafes_end.png", 6.4),
          p("Figure 7. Distance and altitude, pack voltage with the failsafe thresholds, and (bottom) the GPS-glitch reports with the mesh ping blackouts.", S),
          bl(f"<b>The pack was already at the low-battery line at the far point</b> ({F['v_low']:.2f} V, {F['t_low_rel']:.0f} s into the flight). The failsafe did what it is set to do and sent the aircraft home in RTL at about 10 m/s, 3.1 km away."),
          bl(f"On the way home the voltage kept falling slowly to {F['v_crit']:.2f} V and the critical failsafe started a Land at {F['dist_land_start']:.0f} m from home and {F['alt_land_start']:.0f} m altitude. "
             f"As the aircraft descended and the motors worked harder, the pack voltage <b>collapsed</b> from 13 V to {F['v_end']:.1f} V in about 40 s. Two of the four motor outputs were near their maximum (about {F['motor_out_end_us'][1]:.0f} and {F['motor_out_end_us'][3]:.0f} microseconds) at the end, and the flight controller reported thrust loss."),
          bl(f"The log ends {F['end']['dist']:.0f} m from home at {F['end']['alt']:.0f} m altitude, still descending. That is consistent with an uncontrolled or hard landing short of the launch point."),
          bl("<b>That is also why the Pi lost power.</b> The Pi's last record is about 25 s before the flight controller's, when the pack was below about 12 V and the Pi's power supply dropped out. The Pi stopped because the whole aircraft's battery gave out, not because of a fault in the Pi alone. Check it for crash damage as well."),
          bl("This matches the 2 October flight, where 1.5 km out and back used about 80% of the same pack. A 3.2 km out-and-back flight, over twice the distance, needed roughly 2.5 to 3 times the energy that pack holds, so the failsafes were bound to trigger. The battery thresholds were left at their saved values, as you asked.")]

story += [p("5. Video and latency", H2),
          p("<b>Video:</b> no video quality or video latency can be reported. The video recording, the QGC logs and the latency test footage were not available. "
            "The ping delay above is the delay of the mesh link itself, not of video, and video adds the camera, encoder and player delays on top.", B),
          p(f"<b>Mesh delay against distance:</b> the median round-trip delay to RN03 was {R['ping_bins']['rn03_ground'][0]['med']:.1f} ms in the first 500 m and {R['ping_bins']['rn03_ground'][2]['med']:.1f} ms at 1 to 1.5 km. "
            f"Beyond 2.5 km it was {R['ping_bins']['rn03_ground'][4]['med']:.0f} to {R['ping_bins']['rn03_ground'][6]['med']:.0f} ms, with spikes of 200 to 425 ms. This fits the radio dropping to a slower bit rate and retrying more at long range. A video stream would feel this as extra delay and bursts of freezes.", B)]

story += [p("6. Estimated reliable range and link margin", H2)]
rows = [["Link", "Tested to", "Result", "Limit found?"],
        ["Mesh traffic out to the far point (pings to RN03)", f"{R['max_3d']:.0f} m (3D) at 220 m altitude", "Outbound: no blackouts. Delay rose beyond 2.5 km.", "No, but delay and retries were rising"],
        ["Mesh traffic back from the far point", "same distances", "three 5 to 6 s blackouts between 1.5 and 2.2 km", "Reliability problem, not a clear distance limit"],
        ["Video", "-", "not measured", "Unknown"]]
story += [table(rows, [2.0, 1.5, 2.2, 1.3]), Spacer(1, 4),
          p(f"<b>Link-margin estimate (rough, not a measurement).</b> Free-space path loss at 907 MHz is about {R['fspl_1500']:.0f} dB at 1.5 km and {R['fspl_far']:.0f} dB at the far point. "
            f"The drone radio read {R['far_rssi_drone']:.0f} dBm there against a noise floor of {R['far_noise_drone']:.0f} dBm, an SNR of about {R['far_snr_drone']:.0f} dB. "
            "A mesh radio at its slowest setting usually needs only a few dB of SNR, so there was probably 8 to 12 dB of margin left on the weakest direction at 3.16 km. "
            "Every doubling of distance in clear air costs about 6 dB, so the margin suggests the clear-air limit is somewhere beyond 5 km, but real terrain, the antenna orientation effect above, and the airframe will shrink that. "
            "Treat it as 'at least 3.2 km with 220 m altitude' and not a promise about anything farther. The ground radio's end had far more margin (SNR near 40 dB).", B)]

story += [p("7. What the data does not show, and what to do next", H2),
          bl("<b>Where the aircraft came down and in what condition.</b> The flight controller's log ends at 18 m altitude, 249 m from home. Whether it hit the ground there, and what was damaged, is not in the data."),
          bl("<b>Video and QGC data</b> (see section 4), and the latency test on the ground."),
          bl("<b>Why the return was worse.</b> Fly the same route with the aircraft kept pointing the same way both ways (or hover facing each way at 2 km), and note the antenna positions on the aircraft. Also repeat the return at a different altitude."),
          bl("<b>Pi and radio hardware.</b> The Pi lost power because the pack collapsed, then the aircraft likely came down. Inspect the Pi, its camera ribbon and the radio for damage before the next flight."),
          bl("<b>Altitude effects.</b> This flight climbed with distance (to 220 m), so distance and altitude can't be separated. A flat-altitude run at a low height would show what low-altitude missions can expect, which will be worse."),
          bl("<b>Antenna orientation, interference sources and longer distance:</b> each needs its own run. The noise floor stayed flat, so no interference was seen on this flight."),
          p("<b>Conclusions</b>", B),
          bl("The mesh link carried traffic and kept the radios reachable to 3.16 km at 220 m altitude with no blackouts on the outbound leg."),
          bl("The link was less reliable on the return, probably because of how the drone-side antennas face the ground radio on that heading. This is the next thing to test."),
          bl("<b>The battery ended the flight.</b> The mission was too long for this pack. A shorter mission, a bigger pack, or finding out why the aircraft draws about 28 A, are the options; the failsafe settings are unchanged."),
          bl("The logging fixes worked: radio signal, SNR, bit rate, retries and the drone's position were all recorded together, and the data survived the Pi losing power."),
          Spacer(1, 6),
          p("Files: flight_2026-10-05\\data (the Pi's flight session log), fc\\log18.bin (flight controller log), results_mesh.json, results_fc.json, charts\\m*.png (separate chart images), analyze_mesh.py, analyze_fc18.py and build_mesh_report.py.", S)]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.65 * inch, bottomMargin=0.65 * inch,
                        title="3 km mesh range test: mesh link report, 2026-10-05")
doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=lambda c, d: (c.setFont("Helvetica", 7.5), c.drawString(0.7 * inch, 0.4 * inch, "Mesh range test 2026-10-05"), c.drawRightString(7.8 * inch, 0.4 * inch, f"page {d.page}")))
print("wrote", OUT)
