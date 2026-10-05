"""Build the PDF report from results.json and the charts. Run after analyze_flight.py."""
import json
import numpy as np
from pymavlink import mavutil
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

R = json.load(open("results.json"))
OUT = "RANGE_TEST_REPORT_2026-10-02.pdf"

# time the pack first read below 14.8 V for 10 s (my recommended low-battery threshold), from the log
m = mavutil.mavlink_connection("fc/log17.bin")
bt, bv, pos_t, pos_alt = [], [], [], []
while True:
    x = m.recv_match(type=["BAT", "POS"])
    if x is None:
        break
    if x.get_type() == "BAT":
        bt.append(x.TimeUS / 1e6); bv.append(x.Volt)
    else:
        pos_t.append(x.TimeUS / 1e6); pos_alt.append(x.RelHomeAlt)
bt, bv = np.array(bt), np.array(bv)
t_to = pos_t[int(np.argmax(np.array(pos_alt) > 5))]
below = bv < 14.8
t148 = None
for i in range(len(bt)):
    if below[i] and (bt[i:] < bt[i] + 10).sum() > 0 and below[(bt >= bt[i]) & (bt <= bt[i] + 10)].all() and bt[i] > t_to:
        t148 = bt[i] - t_to
        break

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15, spaceAfter=6, textColor=colors.HexColor("#0d2b4e"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], keepWithNext=1, fontSize=12, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#0d2b4e"))
B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9.3, leading=12.5, spaceAfter=4)
S = ParagraphStyle("S", parent=B, fontSize=8, leading=10.5, textColor=colors.HexColor("#444444"))
CELL = ParagraphStyle("C", parent=B, fontSize=8.4, leading=10.5, spaceAfter=0)
BUL = ParagraphStyle("BUL", parent=B, leftIndent=12, bulletIndent=2)


def p(t, st=B): return Paragraph(t, st)
def bl(t): return Paragraph(t, BUL, bulletText="-")
def img(path, w=7.0):
    from PIL import Image as PI
    iw, ih = PI.open(path).size
    return Image(path, width=w * inch, height=w * inch * ih / iw)
def table(rows, widths, head=True, zebra=True):
    data = [[Paragraph(str(c), CELL) for c in r] for r in rows]
    t = Table(data, colWidths=[w * inch for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#bbbbbb")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe8f3"))]
    if zebra:
        st += [("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")])]
    t.setStyle(TableStyle(st))
    return t


def mmss(s): return f"{int(s // 60)}:{int(s % 60):02d}"


story = []
story += [p("1.5 km mesh range test: flight report", H1),
          p("Flight of 2 October 2026, Clark Range / Fort McClellan airfield, Alabama. 10-inch quad (Lumenier LUX F765, ArduCopter 4.7.1, 4S 5200 mAh). "
            "Source: the flight controller's onboard log (log #17). <b>This report covers the flight itself and the two link records the flight controller keeps. "
            "It does not contain mesh-radio signal data or video, because neither was recorded. Section 7 explains what is missing and how to capture it next time.</b>", B)]

story += [p("1. Test summary", H2)]
rows = [["Item", "Result", "Plan"],
        ["Date, takeoff, landing (local, CDT)", f"{R['date_local']}, {R['takeoff_local']} to {R['land_local']}", "-"],
        ["Time armed / airborne", f"{mmss(R['armed_s'])} / {mmss(R['airborne_s'])} (mm:ss)", "about 8.7 min estimated"],
        ["Route", "Route B: 17 waypoints, out and back, same waypoints both ways (the file range_test_1500m_north.waypoints)", "same"],
        ["Mission", f"Auto mode flew the mission from takeoff; it reached the last waypoint and RTL began {mmss(R['t_rtl_rel'])} after takeoff", "-"],
        ["Maximum distance from home", f"{R['max_h']:.0f} m horizontal, {R['max_3d']:.0f} m in 3D (reached {mmss(R['far_rel'])} after takeoff)", "1500 m"],
        ["Maximum altitude above home", f"{R['max_alt']:.1f} m ({R['max_alt'] * 3.281:.0f} ft); {R['max_alt_msl']:.0f} m above sea level", "200 m"],
        ["Speed in cruise", f"mean {R['cruise_mean']:.1f} m/s, median {R['cruise_median']:.1f} m/s, peak {R['cruise_max']:.1f} m/s (outbound)", "10 m/s"],
        ["Average speed over the whole leg", f"{R['moving_avg_out']:.1f} m/s outbound including turns and the climb-out; {R['moving_avg_all']:.1f} m/s for the whole flight including the hold and landing", "10 m/s"],
        ["Path flown", f"{R['out_len']:.0f} m outbound, {R['ret_len']:.0f} m return", "about 1950 m each way"],
        ["Route tracking", f"mean {R['xt_mean']:.1f} m from the planned line, 95% within {R['xt_p95']:.1f} m, worst {R['xt_max']:.1f} m; altitude within {R['alt_err_max']:.1f} m of plan", "-"],
        ["GPS", f"at least {R['nsats_min']} satellites, HDOP at most {R['hdop_max']:.2f} throughout", "-"]]
story += [table(rows, [1.9, 3.6, 1.5]), Spacer(1, 6)]
story += [p(f"<b>In short:</b> the aircraft flew the whole planned route, reaching {R['max_h']:.0f} m out at {R['max_alt']:.0f} m altitude, held the 10 m/s speed and stayed within a few metres of the planned line. "
            f"The <b>battery</b> was the limiting factor: the low-battery warning came at {mmss(R['t_fs_rel'])} after takeoff, just as the mission finished (section 3).", B)]
story += [img("charts/01_flight_profile.png", 6.0), p("Figure 1. Distance, altitude and ground speed. The dips in speed are the turns at waypoints. The flat section at 1520 m is the 30 s loiter at the far point.", S)]

story += [p("2. Route and tracking", H2),
          img("charts/06_track_map.png", 3.6),
          p("Figure 2. The flown track (blue out, orange back) lies on the planned waypoints. The red crosses are the two one-second gaps in the ground-station telemetry uplink (section 4).", S),
          img("charts/05_route_tracking.png", 6.4),
          p("Figure 3. Distance from the planned route and altitude error during the flight.", S)]

story += [p("3. Battery", H2)]
rows = [["Moment", "Pack voltage", "Per cell"],
        ["Before takeoff (resting)", f"{R['v0']:.2f} V", f"{R['v0'] / 4:.2f} V"],
        ["Hovering just after takeoff", f"{R['v_hover']:.2f} V", f"{R['v_hover'] / 4:.2f} V"],
        ["At the far point (hold)", f"{R['v_at_far']:.2f} V", f"{R['v_at_far'] / 4:.2f} V"],
        [f"Low-battery failsafe at {mmss(R['t_fs_rel'])}", f"{R['v_fs']:.2f} V", f"{R['cell_fs']:.2f} V"],
        ["Lowest reading", f"{R['vmin']:.2f} V", f"{R['vmin'] / 4:.2f} V"],
        ["15 s after the motors stopped (still rising)", f"{R['v_rest_end']:.2f} V", f"{R['v_rest_end'] / 4:.2f} V"]]
story += [table(rows, [3.2, 1.6, 1.6]), Spacer(1, 4), img("charts/02_battery.png", 6.6),
          p("Figure 4. Pack voltage against the saved failsafe thresholds.", S)]
MAH_IN = 4147.0
avg_a = MAH_IN / 1000.0 / (R["armed_s"] / 3600.0)
story += [p("<b>Measured with the charger.</b> After the flight the charger put back <b>4147 mAh</b>, which is <b>%.0f%%</b> of the pack's rated 5200 mAh. "
            "The pack sat for three days before charging, and charging is a little less than 100%% efficient, so the flight used roughly 3900 to 4150 mAh (75 to 80%% of the rating). "
            "That leaves about 20 to 25%% in the pack at landing, <b>below the 30%% reserve</b>, and is consistent with the resting voltage after landing. "
            "Averaged over the %s the aircraft was armed, that is about %.0f A, or roughly 400 W. The pre-flight estimate used 220 W (about 14 A), so real power was close to twice the guess. "
            "(If the pack has aged below 5200 mAh, the percentage used is higher still.)" % (100 * MAH_IN / 5200, mmss(R["armed_s"]), avg_a), B), Spacer(1, 4)]
story += [p("<b>What it shows</b>", B),
          bl(f"The low-battery warning (saved setting {R['params']['BATT_LOW_VOLT']:.1f} V) fired at {R['v_fs']:.2f} V, {mmss(R['t_fs_rel'])} after takeoff, almost exactly when the mission's own RTL began. "
             f"It did not cause a landing short of the plan, but there was no margin left: the pack stayed below the warning level for the rest of the flight, and it only recovered to {R['v_rest_end']:.2f} V ({R['v_rest_end'] / 4:.2f} V per cell) within 15 s of the motors stopping."),
          bl("A 4S LiPo reading about 3.6 V per cell near the end of a flight is typically close to empty (roughly 10 to 25% left, depending on the pack's age and how hard it was being drawn). "
             "<b>The 30% reserve rule was very probably not met.</b>"),
          bl("The pre-flight estimate was 47% of the pack used (53% remaining, nominal case) and 41% remaining even in the high-power case. The charger shows the real use was about 75 to 80%, so the estimate was too optimistic. "
             f"The pack's voltage sag fits a heavy load, possibly with an aged pack: it dropped {R['v0'] - R['v_hover']:.1f} V from rest to hover. The aircraft has no current sensor, so the log itself can't show current."),
          bl(f"The pack first read below 14.8 V (3.70 V per cell, the low-battery value I recommended in the pre-flight plan) {mmss(t148)} after takeoff, "
             "which is while the aircraft was holding at the far point (1520 m out, 200 m up). That threshold would have triggered an RTL from the far point, halfway through the mission. "
             "<b>So my recommended 14.8 V is wrong for this pack</b>: its voltage sags too much under load for a voltage threshold to be a good guide. See the recommendations in section 7."),
          bl("The settings in this flight were the saved ones, not the recommended ones: low 14.4 V, critical 13.6 V, WP_SPD 3 m/s, RTL_ALT 50 m, geofence off. "
             "The 10 m/s speed still worked because the mission's speed command overrides WP_SPD, as predicted.")]
story += [p("<b>Direct measurement (please send):</b> the number of mAh your charger puts back into this pack is the best measure of what the flight used. "
            "A 5200 mAh pack that takes back about 4500 mAh or more was nearly empty.", B)]

story += [p("4. Link quality: what the flight controller recorded", H2),
          p("There are two link records in the flight controller log. <b>Neither is the mesh radio's signal strength.</b>", B),
          p("<b>A. Ground-station telemetry uplink.</b> The flight controller counts the MAVLink packets that arrive on its telemetry port (from QGroundControl on the phone, through the Pi) once per second. "
            "QGC sends at least a 1 Hz heartbeat, so a count of zero means that second's packets did not arrive.", B)]
rows = [["Measure", "Result"],
        ["Packets received per second", f"{R['rx_rate_mean']:.2f} on average (the 1 Hz heartbeat)"],
        ["Packets reported dropped by the flight controller", f"{R['rx_dropped']}"],
        ["One-second gaps", f"{len(R['uplink_gaps'])}"]]
story += [table(rows, [3.3, 3.3]), Spacer(1, 4)]
rows = [["Gap at (local)", "Seconds after takeoff", "Distance from home", "Altitude", "Where on the route"],
        *[[g["utc"], f"{g['t_since_takeoff']:.0f}", f"{g['dist3d']:.0f} m (3D)", f"{g['alt']:.0f} m", "dirt-road crossing area, WP4 to WP5 (marsh edge and forest)"] for g in R["uplink_gaps"]]]
story += [table(rows, [1.0, 1.1, 1.3, 0.8, 2.4]), Spacer(1, 4), img("charts/04_telemetry_uplink.png", 6.4),
          p("Figure 5. Telemetry uplink packets per second against time and distance. The two red lines are the only gaps in the whole flight.", S),
          p("The uplink was continuous out to 1.5 km. The two 1-second gaps were at 840 m and 930 m, on the legs through the forest and marsh near WP4 and WP5. They are not at the greatest range, "
            "and the link held at 1520 m, so the gaps look like local shadowing from terrain or trees, or a brief Wi-Fi or radio hiccup, rather than a range limit. This record only shows the "
            "<b>ground-to-drone direction</b>. It does not show whether the drone's telemetry reached the phone (the downlink), which you watched working in QGC.", B)]

story += [p("<b>B. ELRS control link (2.4 GHz).</b> This is the transmitter-to-drone radio, a different radio from the Doodle mesh. It is included because it is the only radio signal the log has.", B),
          p(f"Link quality averaged {R['lq_mean']:.1f}% (outbound {R['lq_out_mean']:.1f}%, return {R['lq_ret_mean']:.1f}%) and never fell below {R['lq_min']:.0f}%. "
            f"It was under 90% for {R['lq_below90_s']:.0f} s in total out of about 520 s, in {R['lq_n_dips']} short dips. There is no trend with distance: the average in each 250 m band is shown below, and the best band is the last one (1500 to 1750 m, near the far point).", B)]
rows = [["Distance band (3D)", "Samples (0.1 s)", "Mean quality", "Worst"]] + \
       [[f"{b['lo']} to {b['hi']} m", b["n"], f"{b['mean']:.1f}%" if b["mean"] else "-", f"{b['min']:.0f}%" if b["min"] else "-"] for b in R["lq_by_bin"]]
story += [table(rows, [2.0, 1.4, 1.4, 1.0]), Spacer(1, 4), img("charts/03_control_link_vs_distance.png", 6.6),
          p("Figure 6. ELRS link quality against 3D distance and altitude. Outbound is blue, return is orange.", S),
          p("The control link had a large margin at 1.5 km. That says nothing about the mesh radios, which are on a different band, but it shows the aircraft was not rolling or shadowing its antennas badly enough to hurt a 2.4 GHz link.", B)]

story += [p("5. Mesh radio, video and latency", H2),
          p("<b>These could not be measured, because the data does not exist.</b>", B),
          bl("<b>Mesh signal (RSSI) and signal-to-noise (SNR):</b> the Pi's mesh logger did not record them. The radio is powered on after the Pi and flight controller (the GPS must acquire satellites before the radio's noise starts), so when the logger connected, the radio's wireless interface was not up yet. The old logger never checked again, so it logged nothing from the radio for the whole run. That is fixed (section 7)."),
          bl("<b>Video quality and latency:</b> there was no video, because of a bad connection between the camera ribbon and the Pi. QGC saved no recording, and no latency test footage was supplied."),
          bl("<b>Which Pi log is this flight:</b> the Pi has no clock battery and its logs are all dated 1 October, so I couldn't match a Pi file to this flight with confidence. I didn't use the Pi files in this report."),
          p("<b>Theoretical link budget (not a measurement).</b> Free-space path loss at 907 MHz over 1500 m is about "
            f"{R['fspl_1500']:.0f} dB. As an illustration only: a radio sending 30 dBm (1 W) with 2 dBi antennas at each end would put about -61 dBm at the far radio in open air. "
            "A mesh radio at the slowest setting (10 MHz, 6.5 Mbit/s) usually needs about -90 to -95 dBm. That would leave roughly 30 dB of margin in free space. Trees, terrain and the radio's real power and antennas "
            "will remove some of it, perhaps 10 to 20 dB. Your earlier ground tests showed -23 to -30 dBm at short range, which fits. The real margin at 1.5 km can only be read from the radio's own RSSI during a flight.", B)]

story += [p("6. Estimated reliable range", H2)]
rows = [["Link", "Tested to", "Result", "Limit found?"],
        ["Telemetry uplink (QGC to drone, through the mesh)", f"{R['max_3d']:.0f} m (3D), 200 m altitude", "Continuous except two 1 s gaps", "No. The limit is beyond 1.5 km."],
        ["ELRS control link (2.4 GHz)", f"{R['max_3d']:.0f} m", f"quality at least {R['lq_min']:.0f}%, no trend with distance", "No"],
        ["Mesh radio signal / margin", "-", "not recorded", "Unknown"],
        ["Video", "-", "no video", "Unknown"]]
story += [table(rows, [2.4, 1.5, 1.8, 1.3]), Spacer(1, 4),
          p("The data supports 'telemetry through the mesh works to at least 1.5 km at 200 m altitude'. It does not tell you how much farther it would go, how much margin remained, or what happens to video.", B)]

story += [p("7. What the data does not show, and what to do next", H2),
          p("<b>Not shown by this data</b>", B),
          bl("Mesh RSSI, SNR, noise, bit rate, retries and packet loss versus distance. Where the mesh link would fail, and how much margin was left at 1.5 km."),
          bl("Downlink (drone to phone) loss, QGC video, video freezes and frame rate, and latency."),
          bl("How much battery was used (no current sensor), apart from what the voltage implies."),
          bl("Anything about low-altitude flight: the whole route climbs to 200 m, which gives a clearer radio path than flying low, so the results may not apply to low-altitude missions."),
          bl("Effects of antenna orientation, a different altitude, interference sources, or a longer distance. Each needs its own test."),
          p("<b>What I fixed for next time (on the Pi)</b>", B),
          bl("The mesh logger now re-checks the radio's wireless interface every second, so it records the radio signal even if the radio starts late."),
          bl("It also records the radio's bit rate, retries, failed transmissions and link state."),
          bl("It listens, read-only, to the telemetry the Pi sends to the phone, and logs the drone's position, altitude, speed and GPS time next to the radio numbers. "
             "That lets the radio data be matched to distance and corrects the Pi's wrong clock, even without the flight controller log."),
          bl("It pings two more possible ground-radio addresses (10.223.196.108 and .148) to find which one answers."),
          p("<b>What you need to do before the next flight</b>", B),
          bl("Keep the phone on a ground radio's Wi-Fi (RN03's radio, as it was this flight), not the drone radio's own Wi-Fi (Meshnet-0610). This flight's evidence fits that: the ground-to-drone link kept working to 1.5 km, which a 5 GHz Wi-Fi link to the drone's own radio could not have done."),
          bl("<b>In QGC, turn on 'Save telemetry log after each flight' and video recording</b> (Application Settings), and check the video source is set."),
          bl("Fix or reseat the camera ribbon on the Pi, then run a short ground test before flying: confirm video in QGC and measure latency (section 10 of the plan)."),
          bl("If you want a Mission Planner .tlog, it needs the Pi filter to send telemetry to the laptop as well (section 13 of the plan). I haven't changed that."),
          bl("Battery: with the measured 4147 mAh, the mission as flown is over budget for a 30% reserve. At about 7.65 mAh per second armed, 70% of 5200 mAh (3640 mAh) lasts about 8 minutes (476 s); the flight took about 9 minutes. "
             "Options: shorten the mission by about a minute (for example a 10 s loiter instead of 30 s, and a far point nearer 1.3 km), use a larger or second pack, or find out why the aircraft draws about 28 A to hover and cruise. "
             "Do not just raise the low-battery voltage to 14.8 V: this pack reads below that under load at the far point."),
          bl("Add a current sensor so the flight controller can count mAh used. Then set the low-battery warning by mAh (for example at 60 to 65% used) as well as by voltage."),
          bl("Record the mAh the charger puts back after every flight. It is the simplest check you have."),
          p("<b>Conclusions</b>", B),
          bl("The aircraft flew the whole 1.5 km out-and-back route accurately, at the planned speed and altitude, and came home on its own."),
          bl("The telemetry link through the mesh held to 1.5 km at 200 m altitude with only two 1-second gaps. The range limit was not reached."),
          bl("The battery was nearly spent when the flight ended (about 4147 mAh of 5200 mAh went back in), below the 30% reserve. Don't extend the distance or the time without a larger pack or a shorter mission, and a current sensor."),
          bl("The mesh signal and the video are the unanswered questions, and the changes above are meant to answer them on the next flight."),
          Spacer(1, 6),
          p("Files: flight_2026-10-02\\fc\\log17.bin (flight controller log), results.json, charts\\*.png (the charts as separate image files), analyze_flight.py and build_report.py (how this report was made).", S)]

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.65 * inch, bottomMargin=0.65 * inch,
                        title="1.5 km mesh range test: flight report, 2026-10-02")
doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=lambda c, d: (c.setFont("Helvetica", 7.5), c.drawString(0.7 * inch, 0.4 * inch, "Range test 2026-10-02"), c.drawRightString(7.8 * inch, 0.4 * inch, f"page {d.page}")))
print("wrote", OUT, "t148", t148)
