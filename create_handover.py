from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(r"C:\Users\ebach\Documents\ChatGPT\10 inch Quad")
OUT = ROOT / "outputs" / "handover"
DOCX = OUT / "10-inch-FPV-drone-handover.docx"
SOURCE_XLSX = ROOT / "outputs" / "component-crosscheck" / "10-inch-FPV-drone-component-crosscheck.xlsx"
XLSX = OUT / "10-inch-FPV-drone-component-crosscheck.xlsx"
ZIP = OUT / "10-inch-FPV-drone-handover-package.zip"

NAVY = "1F4E78"
BLUE = "D9EAF7"
LIGHT = "F2F2F2"
PALE_YELLOW = "FFF2CC"
PALE_RED = "FCE4D6"
PALE_GREEN = "E2F0D9"
GRAY = "666666"


def set_cell_shading(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color="B7B7B7", size="6"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def cant_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit")
    tr_pr.append(el)


def add_hyperlink(paragraph, text: str, url: str, color=NAVY, underline=True):
    part = paragraph.part
    rel_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel_id)
    run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    r_fonts = OxmlElement("w:rFonts")
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        r_fonts.set(qn("w:" + attr), "Calibri")
    r_pr.append(r_fonts)
    c = OxmlElement("w:color")
    c.set(qn("w:val"), color)
    r_pr.append(c)
    if underline:
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        r_pr.append(u)
    run.append(r_pr)
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
    return hyperlink


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("Page ")
    run.font.size = Pt(8)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    paragraph._p.append(fld)


def configure_styles(doc: Document):
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        normal._element.rPr.rFonts.set(qn("w:" + attr), "Calibri")
    normal.font.size = Pt(10)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.08

    title = styles["Title"]
    title.font.name = "Calibri"
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        title._element.rPr.rFonts.set(qn("w:" + attr), "Calibri")
    title.font.size = Pt(25)
    title.font.bold = True
    title.font.color.rgb = RGBColor(0, 0, 0)
    title.paragraph_format.space_after = Pt(8)
    title_ppr = title.element.get_or_add_pPr()
    title_border = title_ppr.find(qn("w:pBdr"))
    if title_border is not None:
        title_ppr.remove(title_border)

    for style_name, size in (("Heading 1", 16), ("Heading 2", 12.5), ("Heading 3", 10.5)):
        style = styles[style_name]
        style.font.name = "Calibri"
        for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
            style._element.rPr.rFonts.set(qn("w:" + attr), "Calibri")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(12 if style_name == "Heading 1" else 8)
        style.paragraph_format.space_after = Pt(4)

    for style_name in ("List Bullet", "List Number"):
        styles[style_name].font.name = "Calibri"
        for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
            styles[style_name]._element.rPr.rFonts.set(qn("w:" + attr), "Calibri")
        styles[style_name].font.size = Pt(10)
        styles[style_name].paragraph_format.space_after = Pt(2)


def add_header_footer(section):
    header = section.header
    p = header.paragraphs[0]
    p.text = "10 inch FPV drone build handover"
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.runs[0].font.size = Pt(8)
    p.runs[0].font.color.rgb = RGBColor(102, 102, 102)
    footer = section.footer
    add_page_number(footer.paragraphs[0])


def add_bullet(doc, text: str, bold_prefix: str | None = None):
    p = doc.add_paragraph(style="List Bullet")
    if bold_prefix and text.startswith(bold_prefix):
        p.add_run(bold_prefix).bold = True
        p.add_run(text[len(bold_prefix):])
    else:
        p.add_run(text)
    return p


def add_number(doc, text: str):
    p = doc.add_paragraph(style="List Number")
    p.add_run(text)
    return p


def add_manual_number(doc, number: int, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.25)
    p.paragraph_format.first_line_indent = Inches(-0.25)
    p.paragraph_format.space_after = Pt(2)
    p.add_run(f"{number}.  ")
    p.add_run(text)
    return p


def normalize_run_fonts(doc: Document):
    def apply_runs(paragraphs):
        for paragraph in paragraphs:
            for run in paragraph.runs:
                run.font.name = "Calibri"
                run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Calibri")
                run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Calibri")
                run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Calibri")
                run._element.get_or_add_rPr().rFonts.set(qn("w:cs"), "Calibri")

    apply_runs(doc.paragraphs)
    for section in doc.sections:
        apply_runs(section.header.paragraphs)
        apply_runs(section.footer.paragraphs)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                apply_runs(cell.paragraphs)


def add_link_line(doc, label: str, url: str):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.18)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(label + "  ")
    r.bold = True
    add_hyperlink(p, url, url)
    return p


def table(doc, headers, rows, widths=None, shade_rows=True, font_size=8.6):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    hdr = t.rows[0]
    set_repeat_table_header(hdr)
    for idx, text in enumerate(headers):
        cell = hdr.cells[idx]
        set_cell_shading(cell, NAVY)
        set_cell_border(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(text)
        r.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)
        r.font.size = Pt(font_size)
        if widths:
            cell.width = Inches(widths[idx])
    for row_idx, values in enumerate(rows):
        row = t.add_row()
        cant_split(row)
        for col_idx, value in enumerate(values):
            cell = row.cells[col_idx]
            set_cell_border(cell)
            if shade_rows and row_idx % 2:
                set_cell_shading(cell, LIGHT)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            r = p.add_run(str(value))
            r.font.size = Pt(font_size)
            if widths:
                cell.width = Inches(widths[col_idx])
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return t


def status_table(doc):
    rows = [
        ("Flight controller", "Lumenier LUX F765 NDAA", "Present", "Exact ArduPilot target and microSD requirement matter"),
        ("ESC", "Orqa 3030 70A 3S to 6S BLHeli 32 4 in 1 V2.2", "Present", "Legacy BLHeli 32 unit, not current AM32 version"),
        ("Frame", "Rekon FPV Rekon10 Pro V2", "Present", "10 inch, 474 mm wheelbase"),
        ("Motors", "iFlight XING2 3110 900KV", "Present", "19 by 19 mm M3 mount"),
        ("Propellers", "Gemfan 1050 Cinelifter 10 by 5 tri blade", "Present", "5 mm hub, motor recommendation mismatch"),
        ("Battery", "Tattu G Tech 5200 mAh 4S 35C XT60", "Present", "4S is the selected build voltage"),
        ("Receiver", "Matek ELRS R24 D 2.4 GHz diversity", "Present", "CRSF on full UART"),
        ("GNSS and compass", "Matek M10Q 5883", "Present", "UART plus I2C"),
        ("Video transmitter", "Rush FPV Tank Solo analog 5.8 GHz", "Present", "Antenna required before power"),
        ("Companion computer", "Raspberry Pi Zero 2 W with 64 GB microSD", "Present", "Dedicated airborne 5 V regulator required"),
        ("Companion camera", "Raspberry Pi Camera Module 2", "Present", "CSI digital camera, not an analog FPV camera"),
        ("Bench power", "CanaKit DCAR 052A5 5 V 2.5 A AC supply", "Present", "Bench only, not an airborne LiPo regulator"),
    ]
    table(doc, ["Subsystem", "Photographed component", "State", "Immediate note"], rows, [1.2, 2.55, 0.75, 2.55], font_size=8.2)


def risk_table(doc):
    rows = [
        ("Critical", "FC to ESC wiring", "The matching 30.5 mm mounting pattern does not prove connector pin compatibility. The LUX kit includes 8 pin JST SH leads, while the Orqa ESC listing does not document a plug compatible harness.", "Map motor outputs, battery voltage, current sense, ESC telemetry and grounds from both boards. Repin or solder to verified pads. Continuity test before connecting the LiPo."),
        ("Critical", "ArduPilot target and boot media", "Lumenier states that the LUX F765 requires a microSD card to boot after ArduPilot or PX4 is installed.", "Use the exact LUXNDAAF7 firmware target and a known good FAT32 microSD. Do not substitute a generic F765 target."),
        ("High", "ESC firmware identity", "The photographed ESC is the older BLHeli 32 V2.2 product. Current Orqa ESC documentation describes an AM32 product and is not interchangeable firmware guidance.", "Read the installed ESC identity through ArduPilot passthrough after wiring is verified. Do not cross flash AM32 firmware without an exact, official hardware target."),
        ("High", "Motor and propeller pairing", "Gemfan recommends 3212 to 3214 motors for the 1050 tri blade. The on hand motors are smaller 3110 units. Mechanical fit alone does not validate current, heat or thrust.", "Perform a restrained one motor thrust and current test on 4S, then inspect temperatures and logs before a four motor test or flight."),
        ("High", "Analog and digital video", "The Raspberry Pi Camera Module 2 outputs CSI digital video and cannot feed the Rush analog VTX directly.", "Use the separate analog FPV camera identified in the inventory for piloting. Treat the Pi camera as a recording or computer vision payload."),
        ("High", "Pi power", "The CanaKit supply accepts AC mains, not 4S LiPo input. The Rush 5 V camera output is far below a sensible Pi power budget.", "Use a dedicated 4S input regulated 5 V BEC for the Pi. Budget at least 3 A and verify ripple, connector polarity and common ground."),
        ("High", "Power system current", "The 4S 5200 mAh 35C pack is nominally rated around 182 A continuous, while published motor peak figures cannot be transferred directly to this prop and voltage combination.", "Treat the XT60, battery leads, ESC, solder joints and current sensor as one system. Use a smoke stopper only for electronics checks, not motor load tests. Log current during controlled testing."),
        ("Medium", "VTX supply rail", "The Tank Solo accepts 7 to 36 V and the LUX offers a switched 10 V VTX rail, but the available page does not establish the rail current margin for maximum VTX output.", "Confirm the LUX manual current rating. Use the 10 V rail only with adequate margin; otherwise use filtered battery voltage. Never power the VTX without an antenna."),
        ("Medium", "2.4 GHz coexistence", "The Pi Zero 2 W Wi Fi and the ELRS receiver share the 2.4 GHz band.", "Separate antennas and wiring. Consider disabling Pi Wi Fi in flight or testing coexistence at intended ELRS power and range."),
        ("Medium", "GNSS compass interference", "The external compass can be disturbed by motors, ESC current, battery leads, VTX and ferrous hardware.", "Mount the module at least 10 cm from high current wiring and propulsion hardware when practical, then calibrate and verify compass consistency."),
        ("Medium", "Propeller hardware", "The official iFlight page describes a 5 mm shaft and M5 nut, but verify the actual motors because distributor descriptions can vary.", "Dry fit a prop and verify shaft diameter, thread direction and nut engagement before ordering or installing locknuts."),
        ("Conditional", "Remote ID", "No Remote ID module was identified in the inventory.", "Add an FAA compliant module only if the intended operation requires it."),
    ]
    t = table(doc, ["Priority", "Topic", "Finding", "Required action"], rows, [0.7, 1.25, 2.6, 2.6], font_size=7.7)
    for row in t.rows[1:]:
        priority = row.cells[0].text
        if priority == "Critical":
            set_cell_shading(row.cells[0], PALE_RED)
        elif priority == "High":
            set_cell_shading(row.cells[0], PALE_YELLOW)
        elif priority == "Conditional":
            set_cell_shading(row.cells[0], BLUE)


def add_component(doc, name, observed, facts, concerns, refs):
    doc.add_heading(name, level=2)
    p = doc.add_paragraph()
    p.add_run("Photographed identification  ").bold = True
    p.add_run(observed)
    for fact in facts:
        add_bullet(doc, fact)
    if concerns:
        p = doc.add_paragraph()
        p.add_run("Integration notes  ").bold = True
        p.add_run(concerns)
    for label, url in refs:
        add_link_line(doc, label, url)


def build_document():
    OUT.mkdir(parents=True, exist_ok=True)
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.62)
    section.bottom_margin = Inches(0.62)
    section.left_margin = Inches(0.68)
    section.right_margin = Inches(0.68)
    add_header_footer(section)
    configure_styles(doc)

    title = doc.add_paragraph(style="Title")
    title.add_run("10 inch FPV drone build handover")
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = subtitle.add_run("Photographed components, references, compatibility findings and continuation brief")
    r.bold = True
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(64, 64, 64)
    meta = doc.add_paragraph()
    meta.add_run("Prepared  ").bold = True
    meta.add_run("4 September 2026\n")
    meta.add_run("Build basis  ").bold = True
    meta.add_run("10 inch quadcopter using the on hand 4S battery and photographed components\n")
    meta.add_run("Purpose  ").bold = True
    meta.add_run("A self contained handover for continuing design, wiring, firmware setup and build validation in a separate chat")

    doc.add_heading("Handover summary", level=1)
    p = doc.add_paragraph()
    p.add_run("The core airframe and electronics are present, but the build is not ready for a direct plug together assembly.").bold = True
    p.add_run(" The main blockers are the undocumented LUX to Orqa harness pinout, exact ArduPilot firmware handling, the unvalidated 3110 motor and 10 by 5 tri blade propeller pairing, separate power for the Raspberry Pi, and the need to keep the digital Pi camera distinct from the analog pilot video system.")
    p = doc.add_paragraph()
    p.add_run("Selected power system  ").bold = True
    p.add_run("4S only for this build phase. The FC, ESC and VTX voltage ranges accept 4S. No 6S replacement is proposed.")

    doc.add_heading("Package contents", level=1)
    add_bullet(doc, "10-inch-FPV-drone-handover.docx — this reference and continuation document")
    add_bullet(doc, "10-inch-FPV-drone-component-crosscheck.xlsx — annotated inventory crosscheck with Present, Missing, Partial, Verify and Conditional sheets")
    add_bullet(doc, "10-inch-FPV-drone-handover-package.zip — both files in one portable archive")

    doc.add_heading("Current component register", level=1)
    status_table(doc)

    doc.add_heading("Compatibility assessment", level=1)
    risk_table(doc)

    doc.add_page_break()
    doc.add_heading("Component references", level=1)
    p = doc.add_paragraph("These links are the primary operating references located for the exact products or the closest authoritative product documentation. Packaging text is treated as identification, not as an instruction to alter firmware or wiring.")
    p.paragraph_format.space_after = Pt(8)

    add_component(doc, "Lumenier LUX F765 flight controller", "Lumenier LUX F765 Flight Controller NDAA, retailer SKU 22726", [
        "STM32F765 flight controller with 30.5 mm mounting, eight UARTs, twelve outputs, microSD slot and regulated accessory rails.",
        "Official product information lists Betaflight, ArduPilot and PX4 support.",
        "Lumenier explicitly states that a microSD card is required to boot when using ArduPilot or PX4.",
        "The package normally includes two 8 pin JST SH cables, but cable presence does not establish Orqa ESC pin compatibility.",
    ], "Use only the exact LUXNDAAF7 ArduPilot target. The Lumenier download marked with bootloader is a DFU first flash image; later Mission Planner custom updates normally use the target specific ArduPilot package. Preserve a known working firmware copy before changing versions.", [
        ("Official product page and downloads", "https://www.lumenier.com/products/lumenier-lux-f765-flight-controller-ndaa"),
        ("Lumenier NDAA declarations", "https://www.lumenier.com/military-and-defense-drones/ndaa-declarations"),
    ])

    add_component(doc, "Orqa 3030 70A BLHeli 32 ESC", "Orqa 3030 70A 3S to 6S BLHeli 32 4 in 1 ESC NDAA, model G24083HR1Z, package revision V2.2", [
        "Four channel 70 A continuous ESC, 80 A for 10 seconds, 30 by 30 mm mounting and DShot support.",
        "This is the legacy BLHeli 32 version shown in the photo, not the current Orqa AM32 product.",
    ], "Do not apply AM32 firmware or assumptions from the current Orqa product page. First confirm board pinout and installed BLHeli 32 identity through a verified connection. Map every FC to ESC conductor before power.", [
        ("Exact legacy product page", "https://www.lumenier.com/products/orqa-3030-70a-3-6s-blheli_32-4-in-1-esc-ndaa"),
        ("Orqa manual portal", "https://orqafpv.com/manual"),
        ("Current AM32 product for distinction only", "https://shop.orqafpv.com/products/orqa-orqa-electronic-speed-controller"),
    ])

    add_component(doc, "Rush FPV Tank Solo video transmitter", "Rush FPV Tank Solo analog 5.8 GHz VTX with MMCX to SMA cable", [
        "Input range 7 to 36 V, 48 channels and selectable PIT, 25, 400, 800 and maximum output modes.",
        "Provides a 5 V camera output rated far below a Raspberry Pi power requirement.",
        "Uses analog video and SmartAudio control.",
    ], "Power from the LUX switched 10 V rail only after confirming regulator current margin; otherwise use filtered battery voltage. Install the antenna before applying power. The Pi Camera Module 2 cannot connect to this VTX.", [
        ("Official product reference", "https://rushfpv.net/products/tank-solo-vtx"),
    ])

    add_component(doc, "Raspberry Pi Zero 2 W", "Raspberry Pi Zero 2 W with a photographed 64 GB microSD card", [
        "Uses a 22 pin, 0.5 mm pitch mini CSI camera connector, microSD storage, mini HDMI and micro USB power.",
        "Official guidance recommends a 2 A supply for the board; attached peripherals add to the power budget.",
        "Onboard Wi Fi operates in the same 2.4 GHz band as the ELRS receiver.",
    ], "Use a dedicated 4S input 5 V regulator sized with margin, ideally at least 3 A for the Pi and camera. Do not power the Pi from the Rush camera output. Test ELRS range with Pi Wi Fi active and disabled.", [
        ("Official product page", "https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/?variant=raspberry-pi-zero-2-w"),
        ("Official Raspberry Pi hardware documentation", "https://www.raspberrypi.com/documentation/computers/raspberry-pi.html"),
        ("Official connector and radio hardware documentation", "https://www.raspberrypi.com/documentation/hardware/rf/"),
    ])

    add_component(doc, "Raspberry Pi Camera Module 2", "Raspberry Pi Camera Module 2, 8 megapixel Sony IMX219", [
        "Fixed focus CSI digital camera supporting common still and video modes.",
        "A Pi Zero camera cable is required because the Pi Zero uses the narrow 22 pin connector while the camera board uses the standard camera connector.",
        "Current Raspberry Pi OS uses rpicam applications and Picamera2; the legacy raspivid and raspistill stack is unsupported.",
    ], "This camera is for recording, computer vision or a companion link. It is not a substitute for the analog FPV camera feeding the Rush VTX.", [
        ("Camera hardware documentation", "https://www.raspberrypi.com/documentation/accessories/camera.html"),
        ("Camera software documentation", "https://www.raspberrypi.com/documentation/computers/camera_software.html"),
        ("Camera Module 2 documentation portal", "https://pip.raspberrypi.com/categories/652-raspberry-pi-camera-module-2"),
    ])

    add_component(doc, "Matek ELRS R24 D receiver", "Matek ELRS-R24-D 2.4 GHz diversity receiver, CRSF, 22.5 dBm telemetry", [
        "Accepts 4 to 9 V and connects by CRSF using a full bidirectional UART.",
        "Receiver RX connects to FC TX and receiver TX connects to FC RX, with 5 V and ground.",
        "ExpressLRS 3 series firmware target is MATEK R24-D 2.4GHz RX.",
    ], "Use a compatible 2.4 GHz ELRS transmitter with matching major firmware, regulatory domain and binding phrase. Keep both antennas clear of carbon, high current wiring, VTX hardware and the Pi radio.", [
        ("Official Matek product manual", "https://www.mateksys.com/?portfolio=elrs-r24"),
        ("ExpressLRS receiver wiring", "https://www.expresslrs.org/quick-start/receivers/wiring-up/"),
        ("ExpressLRS receiver binding", "https://www.expresslrs.org/quick-start/receivers/binding/"),
    ])

    add_component(doc, "Matek M10Q 5883 GNSS and compass", "Matek M10Q-5883 with u-blox M10 GNSS and QMC5883L compass", [
        "Accepts 4 to 9 V and uses a six pin JST GH connection.",
        "GNSS uses a UART while the compass uses I2C clock and data lines.",
        "Matek specifies ArduPilot 4.3 or later and Rotation None for a flat ArduPilot installation.",
    ], "Cross TX and RX, connect SCL and SDA to the FC I2C bus, and keep the module at least 10 cm from high current conductors, ESC, motors and ferrous hardware where practical. Calibrate outdoors after the final installation.", [
        ("Official Matek product manual", "https://www.mateksys.com/?portfolio=m10q-5883"),
        ("ArduPilot compass calibration", "https://www.ardupilot.ardupilot.org/copter/docs/common-compass-calibration-in-mission-planner.html"),
    ])

    add_component(doc, "iFlight XING2 3110 900KV motors", "iFlight XING2 3110 900KV FPV cinelifter motors", [
        "Official listings describe a 19 by 19 mm M3 mount, approximately 77 g mass, 18 AWG leads and a 5 mm prop shaft for the 900KV version.",
        "The official peak current and power data are test point figures and are not a safe prediction for this 4S and Gemfan propeller combination.",
    ], "The motor mount matches the Rekon10 frame. Verify the actual shaft diameter and included M5 hardware. The 3110 motor is smaller than Gemfan's 3212 to 3214 recommendation for the 1050 tri blade, so validation testing is mandatory.", [
        ("Official iFlight EU product page", "https://iflight-rc.eu/en-gb/products/xing2-3110-fpv-cinelifter-motor?variant=45302443573513"),
        ("Official iFlight thrust data search", "https://www.iflight.com/index.php?keyword=33&route=resources%2Ftechnical_support_search&section=support-2-19"),
    ])

    add_component(doc, "Rekon10 Pro V2 frame", "Rekon FPV Rekon10 Pro V2 10 inch frame", [
        "Published specifications list a 474 mm wheelbase, 30.5 by 30.5 and 20 by 20 mm FC mounts, and 19 by 19 mm M3 motor mounts.",
        "VTX mounting patterns include 30.5, 20 and 25.5 mm; camera width is 19 to 20 mm.",
        "Published frame mass is approximately 567 g including hardware.",
    ], "No standalone official assembly manual was located. Dry fit the carbon stack, confirm arm and plate orientation from product images, isolate electronics from carbon edges, and use threadlocker only on metal to metal fasteners.", [
        ("Detailed product dimensions and mounting reference", "https://www.fpv24.com/da/hglrc/hglrc-rekon10-pro-v2-long-range-ramme-10-tommer-o4-kompatibel"),
    ])

    add_component(doc, "Tattu G Tech 5200 mAh 4S battery", "Tattu G-Tech 5200 mAh 14.8 V 35C 4S1P with XT60, SKU TAA52004S35X6", [
        "Published mass is approximately 436.5 g with dimensions about 133 by 45 by 33.5 mm.",
        "Uses an XT60 discharge connector, JST XHR balance connector and 10 AWG leads.",
        "Nominal energy is 76.96 Wh; the label discharge rating corresponds to about 182 A, but system limits may be lower.",
    ], "Confirm secure two strap retention, pad the pack from carbon, and keep balance leads away from propellers. Begin propulsion tests at low duty cycle and use current logging rather than treating the C rating as a guaranteed aircraft current limit.", [
        ("Official Tattu product page", "https://genstattu.com/tattu-5200mah-14-8v-35c-4s1p-lipo-battery-pack-with-xt60-plug.html"),
    ])

    add_component(doc, "Gemfan 1050 Cinelifter propellers", "Gemfan 1050 10 by 5 glass fiber nylon tri blade set, one clockwise and one counterclockwise per pack", [
        "Published mass is 16.8 g per propeller with a 5 mm shaft hole.",
        "Gemfan recommends 3212 to 3214 motors for this propeller.",
        "A quad requires two clockwise and two counterclockwise propellers plus practical spares.",
    ], "Do not install props during firmware, receiver, compass or motor output configuration. Confirm blade orientation and motor direction only after the ArduPilot motor order test. Balance or reject visibly damaged props.", [
        ("Official Gemfan product page", "https://www.gemfanhobby.com/1050-cinelifter-glass-fiber-nylon-3-blade.html"),
    ])

    add_component(doc, "CanaKit 5 V 2.5 A power supply", "CanaKit model DCAR-052A5, 100 to 240 V AC input, 5 V 2.5 A output", [
        "This is an indoor AC mains power adapter suitable for bench power when its connector and polarity match the Pi.",
        "It is not a 4S input BEC and must not be connected to the flight battery.",
    ], "Use for stationary Raspberry Pi setup only. The airborne Pi installation needs a separate regulated DC supply from the 4S power system.", [
        ("UL Product iQ listing for model family", "https://productiq.ulprospector.com/en/profile/2664639/qqjq7.e471380?page=25&term=QQJQ7"),
    ])

    doc.add_page_break()
    doc.add_heading("ArduPilot and Mission Planner", level=1)
    p = doc.add_paragraph()
    p.add_run("Recommended firmware path  ").bold = True
    p.add_run("Start with the Lumenier supplied LUXNDAAF7 ArduCopter image to establish a known board target and bootloader state. If the controller has no compatible bootloader, the Lumenier file named with_bl.hex is a DFU image. Once the correct bootloader is installed and Mission Planner recognizes the board, use only a confirmed LUXNDAAF7 ArduPilot package for later updates. Never select a generic F765 target merely because the processor matches.")

    doc.add_heading("Firmware sequence", level=2)
    steps = [
        "Remove all propellers and disconnect the main battery. Photograph both boards and connector labels before assembly.",
        "Install a known good FAT32 microSD in the LUX F765. Lumenier states that ArduPilot boot requires it.",
        "Connect the FC by USB only. Record the current firmware and board identity before flashing.",
        "For an initial DFU flash, use the exact Lumenier LUXNDAAF7 image that includes the bootloader. For a normal Mission Planner custom update, use the exact target specific ArduPilot firmware package.",
        "After reboot, confirm Mission Planner connects, the board orientation is correct and the SD card is logging.",
        "Wire only the receiver and GNSS next. Configure and verify each UART before adding ESC and VTX power wiring.",
        "Wire the ESC only after a pin by pin map has been documented and checked by continuity meter.",
        "Use DShot so throttle calibration is not required. Start with a conservative DShot rate if signal leads are long; confirm motor order and direction with props removed.",
        "Back up parameters after each stable milestone and name files with the date and hardware state.",
    ]
    for index, item in enumerate(steps, start=1):
        add_manual_number(doc, index, item)

    doc.add_heading("Mission Planner parameter starting points", level=2)
    rows = [
        ("Receiver UART", "SERIALx_PROTOCOL = 23", "CRSF and ExpressLRS require TX and RX on a full UART. Baud is normally detected automatically."),
        ("ESC protocol", "MOT_PWM_TYPE = DShot option supported by the installed ArduPilot version", "DShot requires no ESC throttle calibration. Choose a conservative rate first and follow the exact output group capability."),
        ("GNSS UART", "GPS protocol auto detection initially", "Verify satellites, fix type and update rate outdoors before arming."),
        ("Compass", "External compass enabled, Rotation None for flat Matek mount", "Confirm compass instance and orientation, then calibrate after final mounting."),
        ("Logging", "SD logging enabled", "Confirm log creation before motor load testing."),
        ("Frame", "Quad X only after motor layout is verified", "Use Mission Planner motor test at very low power with props removed."),
    ]
    table(doc, ["Function", "Starting point", "Validation"], rows, [1.25, 2.2, 3.7], font_size=8.2)

    doc.add_heading("Official ArduPilot references", level=2)
    for label, url in [
        ("Mission Planner firmware loading", "https://ardupilot.ardupilot.org/planner/docs/common-loading-firmware-onto-pixhawk.html"),
        ("Mission Planner custom firmware", "https://ardupilot.org/planner/docs/common-custom-firmware.html"),
        ("Mission Planner initial setup", "https://ardupilot.org/planner/docs/mission-planner-initial-setup.html?highlight=joystick"),
        ("Mandatory hardware configuration", "https://ardupilot.org/copter/docs/configuring-hardware.html?highlight=mission"),
        ("Motor order and motor test", "https://en.ardupilot.org/copter/docs/connect-escs-and-motors.html"),
        ("DShot ESC setup", "https://ardupilot.org/copter/docs/common-dshot-escs.html?highlight=blheli"),
        ("BLHeli 32 passthrough and firmware warning", "https://en.ardupilot.org/copter/docs/common-blheli32-passthru.html"),
        ("CRSF and ELRS radio setup", "https://ardupilot.org/copter/docs/common-rc-systems.html?highlight=sbus"),
        ("Typical flight controller wiring", "https://ardupilot.org/copter/docs/common-flight-controller-wiring.html"),
    ]:
        add_link_line(doc, label, url)

    doc.add_heading("Wiring and integration notes", level=1)
    rows = [
        ("4S battery", "Orqa ESC battery pads through XT60 and low ESR capacitor", "Observe polarity, strain relief and insulation. First electronics power up through a smoke stopper."),
        ("Orqa ESC", "LUX motor outputs M1 to M4 plus ground and any verified telemetry, current and voltage signals", "No blind connector use. Build and sign off a pin map first."),
        ("ELRS R24 D", "One full LUX UART with TX and RX crossed, 5 V and ground", "SERIALx_PROTOCOL 23. Never feed VBAT."),
        ("M10Q 5883", "One UART for GNSS plus I2C SCL and SDA, 5 V and ground", "Mount remotely and verify orientation."),
        ("Tank Solo", "Analog camera video input, LUX SmartAudio UART TX, ground and a verified supply rail", "Antenna attached before power. The Pi camera is not connected here."),
        ("Analog FPV camera", "Tank Solo video input and suitable regulated supply", "Use the camera voltage range from its own manual."),
        ("Pi Zero 2 W", "Dedicated 5 V BEC from 4S; optional MAVLink UART with common ground", "Confirm UART voltage level and disable any console on the selected serial port."),
        ("Pi Camera 2", "CSI ribbon through a Pi Zero 22 pin camera cable", "Route away from sharp carbon and propeller arcs."),
    ]
    table(doc, ["Device", "Connection concept", "Critical check"], rows, [1.15, 3.0, 3.0], font_size=8.1)

    doc.add_heading("Mechanical and RF layout", level=2)
    mechanical_items = [
        "Place the FC on soft grommets with its orientation recorded. Keep the ESC and high current battery loop compact.",
        "Mount the M10Q 5883 away from motors, ESC, battery leads, VTX and steel fasteners. A rear mast is preferable if it stays clear of propellers.",
        "Mount the two ELRS antennas as a true diversity pair with different orientations and clear of carbon. Keep them separated from the 5.8 GHz VTX antenna and Pi Wi Fi antenna area.",
        "Use two battery straps and a non slip pad. The published frame plus battery plus four motors is already about 1.31 kg before electronics, wiring, antennas and payload.",
        "Use Kapton or fishpaper at carbon contact points, protect wire exits with braid or spiral wrap, and apply removable blue threadlocker only to clean metal to metal threads.",
    ]
    for item in mechanical_items:
        add_bullet(doc, item)

    doc.add_heading("Safety and first power sequence", level=1)
    safety_items = [
        "Props remain off for all firmware, radio, GPS, VTX control, motor order and motor direction work.",
        "Continuity check the battery input for a short and verify XT60 polarity before connecting any pack.",
        "Use a smoke stopper for the first low load electronics power up. It is not used for motor thrust testing.",
        "Attach a rated 5.8 GHz antenna to the VTX before the VTX receives power.",
        "Verify every regulated rail with a multimeter before plugging in the FC, receiver, GPS, VTX, analog camera or Pi.",
        "Perform failsafe, arming switch, mode switch, GPS, compass and motor order checks before installing props.",
        "For the first propeller test, restrain the test article, measure current, monitor motor and ESC temperature, and stop immediately for vibration, desynchronization, excessive current or heat.",
        "Charge and store the LiPo with an appropriate balance charger in a fire resistant location. Inspect the pack after every high current test.",
    ]
    for index, item in enumerate(safety_items, start=1):
        add_manual_number(doc, index, item)

    doc.add_heading("Open items from crosscheck", level=1)
    p = doc.add_paragraph("The accompanying workbook is the authoritative item by item crosscheck. It treats every inventory row as available regardless of wishlist or order status, as requested.")
    p.paragraph_format.space_after = Pt(7)
    rows = [
        ("Missing", "M5 propeller locknuts", "Verify actual motor shaft and thread before purchase."),
        ("Missing", "FC to ESC 8 pin harness", "The LUX box may include JST SH leads, but an electrically compatible Orqa harness is not established. This remains missing until pin compatibility is verified."),
        ("Missing", "Kapton tape or fishpaper", "Electrical isolation from carbon and sharp edges."),
        ("Missing", "Foam or 3M VHB tape", "Mounting and vibration control."),
        ("Missing", "Braided sleeve or spiral wrap", "Wire abrasion protection."),
        ("Missing", "Self powered lost model buzzer", "Recovery after main battery separation."),
        ("Missing", "Propeller balancer", "Useful for validating large tri blades."),
        ("Partial", "M3 hardware set", "Screws present; standoffs, washers and locking nuts not confirmed."),
        ("Partial", "Zip tie anchors", "Zip ties present; adhesive or screw anchors not confirmed."),
        ("Partial", "Equipment mounts", "ELRS and standard camera mounts present; GNSS, Pi and Pi camera mounts not confirmed."),
        ("Verify", "Blue removable threadlocker", "Generic Loctite appears in inventory; confirm it is removable medium strength, not permanent."),
        ("Conditional", "FAA approved Remote ID module", "Only if required for the planned operation."),
    ]
    t = table(doc, ["Crosscheck state", "Item", "Handover note"], rows, [1.0, 2.45, 3.7], font_size=8.2)
    for row in t.rows[1:]:
        state = row.cells[0].text
        if state == "Missing":
            set_cell_shading(row.cells[0], PALE_RED)
        elif state in ("Partial", "Verify"):
            set_cell_shading(row.cells[0], PALE_YELLOW)
        else:
            set_cell_shading(row.cells[0], BLUE)

    doc.add_heading("Decisions already made", level=1)
    for item in [
        "Use the on hand 4S battery for the current build phase.",
        "Do not recommend replacements for photographed or inventoried parts merely because another option may be preferable.",
        "Identify only additional materials, interfaces or safety items needed to make the existing component set work.",
        "Treat wishlist, ordered and on hand spreadsheet rows as accessible for crosscheck purposes.",
    ]:
        add_bullet(doc, item)

    doc.add_heading("Next chat starting point", level=1)
    p = doc.add_paragraph()
    p.add_run("Upload this DOCX and the XLSX, then paste the following request into the new chat.").bold = True
    prompt = (
        "Continue the 10 inch FPV drone build from the attached handover and component crosscheck. "
        "Keep the build on 4S and do not recommend replacements for components already present. "
        "First produce a verified pin by pin wiring plan for the Lumenier LUX F765, legacy Orqa 3030 70A BLHeli 32 V2.2 ESC, Matek ELRS R24 D, Matek M10Q 5883, Rush Tank Solo, analog FPV camera and dedicated Pi power regulator. "
        "Explicitly resolve the FC to ESC harness pinout before any plug connection. Then create the ArduPilot Mission Planner setup sequence and a restrained propulsion validation plan for the XING2 3110 900KV motors with Gemfan 1050 tri blade props on the Tattu 4S pack. "
        "Flag any facts that still require a board photo, continuity test or manual confirmation."
    )
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.25)
    p.paragraph_format.right_indent = Inches(0.25)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    set_cell = None
    run = p.add_run(prompt)
    run.italic = True
    run.font.size = Pt(9.2)

    doc.add_heading("Information to capture next", level=2)
    for item in [
        "Clear top and bottom photographs of the LUX F765 and Orqa ESC with all pad labels visible.",
        "The exact 8 pin cables found inside the LUX box and the connector fitted to the Orqa ESC, including wire colors and connector keying.",
        "Analog FPV camera make, model and voltage range.",
        "On aircraft 5 V BEC model and rating intended for the Pi.",
        "Radio transmitter and ELRS module model, firmware major version and regulatory domain.",
        "Measured motor shaft diameter, prop fit, vehicle all up weight and any bench current data.",
    ]:
        add_bullet(doc, item)

    doc.add_heading("Handover limitations", level=1)
    limitations = doc.add_paragraph(
        "This document consolidates product pages and official project documentation available at preparation time. It does not replace board level pinout confirmation, continuity testing, local flight regulations or controlled propulsion testing. The Rekon10 frame did not yield a standalone manufacturer assembly manual, and an exact standalone manual for the CanaKit adapter was not located; the cited references and photographed labels are used for those items."
    )
    for run in limitations.runs:
        run.font.size = Pt(9.5)

    doc.core_properties.title = "10 inch FPV drone build handover"
    doc.core_properties.subject = "Component references, compatibility assessment and continuation brief"
    doc.core_properties.author = "OpenAI Codex"
    doc.core_properties.keywords = "FPV, ArduPilot, Mission Planner, LUX F765, Orqa, 4S, handover"
    normalize_run_fonts(doc)
    doc.save(DOCX)


def package_files():
    shutil.copy2(SOURCE_XLSX, XLSX)
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(DOCX, DOCX.name)
        zf.write(XLSX, XLSX.name)


if __name__ == "__main__":
    build_document()
    package_files()
    print(DOCX)
    print(XLSX)
    print(ZIP)
