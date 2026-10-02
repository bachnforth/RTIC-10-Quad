import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "C:/Users/ebach/Documents/ChatGPT/10 inch Quad/outputs/component-crosscheck";
const previewDir = "C:/Users/ebach/Documents/ChatGPT/10 inch Quad/outputs/component-crosscheck-build/previews";
const outputPath = `${outputDir}/10-inch-FPV-drone-component-crosscheck.xlsx`;
const sourceName = "On_Hand_and_Ordered.xlsx";

const rows = [
  [1,"Required additions","Three additional iFlight XING2 3110 900KV motors","3 additional motors","Present","iFlight XING2 3110 Cinelifter Motor - 900KV; quantity 120","Equipment Distribution!A393:D393","Spreadsheet quantity is more than sufficient for a four-motor build."],
  [2,"Required additions","Additional Gemfan 1050 propeller package","Enough for 2 CW and 2 CCW props","Present","Gemfan Cinelifter 1050 reinforced glass-fiber nylon props; quantity 54","Equipment Distribution!A402:D402","Confirm each package contains the required CW/CCW pair arrangement before assembly."],
  [3,"Required additions","Analog FPV camera","19-20 mm, CVBS, compatible with Rush analog VTX","Present","Fat Shark Aura Analog FPV Camera and FPV Analog Cameras inventory","Equipment Distribution!A422:D422; A431:D431","Select a camera with CVBS output and a frame-compatible mounting width."],
  [4,"Required additions","Separate microSD card for LUX F765","Preferably 8-32 GB, FAT32","Present","SanDisk 32GB Ultra microSDHC cards","Equipment Distribution!A377:D377","Use a dedicated card for the flight controller; keep the 64GB card for the Raspberry Pi."],
  [5,"Required additions","Regulated 5V BEC for Raspberry Pi","4S input; at least 3A output","Present","DROK 9-36V to 5V, 3.5-6A buck converter","Equipment Distribution!A367:D367","A 4S pack is within the listed input range."],
  [6,"Required additions","Raspberry Pi camera ribbon cable","15-pin to 22-pin Standard-to-Mini CSI cable","Present","Arducam kit includes 15-to-22-pin ribbon; separate 22-to-15-pin CSI cable also listed","Equipment Distribution!A417:D419","Choose the length that reaches the Pi without folding sharply or contacting propellers."],
  [7,"Required additions","XT60 battery pigtail for ESC","XT60 with suitable high-current silicone wire","Present","XT60 male/female connectors with 14AWG silicone wire","Equipment Distribution!A293:D293","Use the connector polarity required by the battery and verify it before soldering."],
  [8,"Required additions","Low-ESR capacitor for ESC battery pads","Approximately 1000-2200uF, 35-50V","Present","35YXJ1000M12.5X20 capacitor; quantity 50","Equipment Distribution!A357:D357","The listed part appears to be a 35V 1000uF YXJ-series capacitor; verify markings before installation."],
  [9,"Required additions","M5 propeller locknuts","4 locknuts/nyloc nuts","Missing","No M5, locknut, or nyloc-nut entry found","Full inventory cross-check","Confirm whether the XING2 motors include locknuts; otherwise obtain four."],
  [10,"Required additions","Strong battery straps","At least 2 suitable straps","Present","16mm x 400mm rubberized straps and 15mm x 250mm UAV battery straps","Equipment Distribution!A292:D304; A414:D414","Use straps long enough to pass through the Rekon10 frame and fully overlap around the 4S pack."],
  [11,"Required additions","4S LiPo balance charger and XT60 connection","Charger supporting 4S LiPo plus balance and main leads","Present","Hota D6 Pro, iCharger 465 Duo, 4S balance lead, and XT60 connector entries","Equipment Distribution!A285:D285; A293:D293; A345:D346","Verify the charger's output connection and balance-board wiring before charging."],
  [12,"Required additions","2.4GHz ExpressLRS transmitter or ELRS radio","Compatible with Matek ELRS-R24-D receiver","Present","RadioMaster radios and Nomad transmitter module","Equipment Distribution!A279:D280; A490:D490","Confirm the selected radio/module is configured for 2.4GHz ExpressLRS."],
  [13,"Required additions","5.8GHz analog FPV goggles or receiver/monitor","Analog 5.8GHz video reception","Present","Orca goggles and Analog Fat Shark receiver module","Equipment Distribution!A239:D239; A253:D253","Confirm the receiver module is installed and compatible with the goggles."],
  [14,"Required additions","Matching goggle antenna","5.8GHz antenna with correct connector and polarization","Present","Several 5.8GHz RHCP/LHCP SMA antennas and a goggle antenna set","Equipment Distribution!A66:D80","Match RHCP/LHCP polarization and SMA/RP-SMA connector type to the selected VTX and goggles."],
  [15,"Wiring and mounting","JST-SH 1.0mm connector/pigtail assortment","For LUX F765 flight-controller ports","Present","JST Connector Kit 1.0mm Pitch","Equipment Distribution!A370:D370","Verify that the kit is JST-SH rather than another 1.0mm series and that housings, crimps, or pigtails are included."],
  [16,"Wiring and mounting","8-pin flight-controller-to-ESC harness","Wire to the verified LUX F765 and Orqa ESC pinouts","Missing","No 8-pin or FC-to-ESC harness entry found","Full inventory cross-check","Do not assume the pin order matches at both ends; continuity-check every conductor."],
  [17,"Wiring and mounting","M3 FC/ESC mounting hardware","Standoffs, screws, washers, and locking nuts","Partial","M3 screws in several lengths are listed; standoffs, M3 washers, and M3 locking nuts are not","Equipment Distribution!A210:D215","Add the missing mounting pieces or verify they are included with the frame/stack."],
  [18,"Wiring and mounting","Spare M3 motor screws","Length appropriate for Rekon10 arms and XING2 motors","Present","M3 screws in 5, 6, 8, 10, and 12mm lengths","Equipment Distribution!A210:D215","Confirm screw length cannot contact the motor windings."],
  [19,"Wiring and mounting","Heat-shrink tubing","Assorted sizes for signal and power wiring","Present","Heat-shrink rolls and assorted kits","Equipment Distribution!A142:D167; A335:D335","Use the smallest size that fully covers each joint after shrinking."],
  [20,"Wiring and mounting","Kapton tape or fishpaper","Electrical insulation around boards and high-current connections","Missing","No Kapton tape or fishpaper entry found","Full inventory cross-check","Keep conductive carbon-fiber surfaces isolated from exposed pads and power connections."],
  [21,"Wiring and mounting","Zip ties and adhesive cable anchors","For strain relief and cable routing","Partial","Several zip-tie entries are listed; adhesive cable anchors/tie mounts are not","Equipment Distribution!A147:D147; A226:D226","Use anchors only where they cannot loosen into a propeller path."],
  [22,"Wiring and mounting","Foam or 3M VHB mounting tape","Electronics-grade vibration-resistant mounting tape","Missing","Generic Alien double-sided tape is listed, but no foam/VHB electronics mounting tape is specified","Equipment Distribution!A144:D145; A218:D219","The generic tape entry was not treated as a confirmed equivalent."],
  [23,"Wiring and mounting","Braided cable sleeve or spiral wrap","Protect and organize exposed wiring","Missing","No braided sleeving, spiral wrap, or wire-loom entry found","Full inventory cross-check","Size it for the motor leads and any external wire bundles that need abrasion protection."],
  [24,"Wiring and mounting","Blue removable threadlocker","Medium-strength removable formulation","Verify","Inventory lists only “Loc-tite,” without color or strength","Equipment Distribution!A227:D227","Confirm it is removable blue threadlocker before using it on metal-to-metal fasteners."],
  [25,"Wiring and mounting","Equipment mounts","GPS, ELRS antennas, Raspberry Pi, and Pi camera","Partial","ELRS antenna and standard camera mounts are listed; dedicated GPS, Pi, and Pi-camera mounts are not","Equipment Distribution!A57:D59; A418:D418","The spreadsheet also lists 3D printers and filament, so the missing mounts may be fabricated."],
  [26,"Strongly recommended","Self-powered lost-model buzzer","Independent battery so it can sound after main-pack separation","Missing","Only smoke-stopper alarm buzzers are listed","Equipment Distribution!A37:D37; A350:D350","A smoke-stopper alarm does not provide lost-model recovery after a crash."],
  [27,"Strongly recommended","4S-compatible smoke stopper","XT60-compatible short-circuit protection","Present","Dedicated smoke-stopper entries for 2-6S systems","Equipment Distribution!A37:D37; A350:D350","Use during initial power-up with propellers removed."],
  [28,"Strongly recommended","Multimeter","Continuity, voltage, polarity, and resistance checks","Present","Fluke 15B+ Digital Multimeter","Equipment Distribution!A165:D165","Check XT60 polarity and continuity before connecting the flight battery."],
  [29,"Strongly recommended","LiPo charging/storage bag or fire-resistant container","Large enough for the 4S battery","Present","Zeee fireproof/explosionproof battery storage guard pouch","Equipment Distribution!A339:D339","Charge on a nonflammable surface and follow the charger and battery manufacturers' instructions."],
  [30,"Strongly recommended","Cell-voltage checker","Supports 4S LiPo","Present","Hitec and ISDT battery checkers/balancers","Equipment Distribution!A308:D311","Verify all four cell voltages before charging and before flight."],
  [31,"Strongly recommended","Small Raspberry Pi heatsink","Sized for Raspberry Pi Zero 2 W","Present","Heat Sink Kits","Equipment Distribution!A476:D476","Confirm the selected heatsink clears the camera cable and nearby components."],
  [32,"Strongly recommended","Propeller balancer","Suitable for 10-inch three-blade propellers","Missing","No propeller-balancer entry found","Full inventory cross-check","Use a balancer that supports the propeller hub diameter and weight."],
  [33,"Strongly recommended","USB-C data cable for LUX F765","Data-capable, not charge-only","Present","USB-C data cable entries","Equipment Distribution!A123:D123; A162:D163","Confirm the chosen cable carries data before troubleshooting the flight-controller connection."],
  [34,"Strongly recommended","Micro-USB data cable for Raspberry Pi","USB-A to Micro-B, data-capable","Present","Several USB-A to Micro-B data cables","Equipment Distribution!A180:D181; A343:D343","Use the Pi's data-capable USB port appropriate to the intended setup."],
  [35,"Strongly recommended","FAA-approved Remote ID module","Only if required for the aircraft and operation","Conditional","No Remote ID module entry found","Full inventory cross-check","Determine whether the build and intended operation require Remote ID before purchase or installation."]
];

const headers = ["ID","Original category","Component or material","Quantity / specification","Cross-check status","Spreadsheet match","Source reference","Annotation"];
const statusInfo = [
  ["Present","A reasonable spreadsheet match was found; wishlist and ordered entries count as available."],
  ["Missing","No matching item was found in the inventory spreadsheet."],
  ["Partial","Part of the combined checklist item is listed, but one or more required pieces are absent."],
  ["Verify","A possible match exists, but the spreadsheet lacks a critical specification."],
  ["Conditional","Not listed, but only needed if the stated regulatory or build condition applies."]
];

const colors = {
  navy: "#24364B", blue: "#356A8A", lightBlue: "#DCEAF2", green: "#E2F0D9",
  red: "#FCE4D6", amber: "#FFF2CC", purple: "#E4DFEC", gray: "#E7E6E6",
  text: "#1F2933", white: "#FFFFFF", line: "#B8C2CC"
};

const wb = Workbook.create();
const summary = wb.worksheets.add("Summary");
const all = wb.worksheets.add("All Items");
const present = wb.worksheets.add("Present");
const missing = wb.worksheets.add("Missing");
const partial = wb.worksheets.add("Partial - Verify");
const conditional = wb.worksheets.add("Conditional");

function styleBase(sheet, usedRange) {
  sheet.showGridLines = false;
  const r = sheet.getRange(usedRange);
  r.format.font = { name: "Arial", size: 10, color: colors.text };
  r.format.verticalAlignment = "top";
}

function addTitle(sheet, title, subtitle) {
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1:H1").format.font = { name: "Arial", size: 16, bold: true, color: colors.navy };
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2:H2").format.font = { name: "Arial", size: 10, italic: true, color: "#52616B" };
  sheet.getRange("A2:H2").format.borders = { bottom: { style: "thin", color: colors.line } };
}

function applyStatusFormatting(sheet, range) {
  const statusRange = sheet.getRange(range);
  statusRange.conditionalFormats.add("containsText", { text: "Present", format: { fill: colors.green, font: { bold: true, color: "#375623" } } });
  statusRange.conditionalFormats.add("containsText", { text: "Missing", format: { fill: colors.red, font: { bold: true, color: "#9C0006" } } });
  statusRange.conditionalFormats.add("containsText", { text: "Partial", format: { fill: colors.amber, font: { bold: true, color: "#7F6000" } } });
  statusRange.conditionalFormats.add("containsText", { text: "Verify", format: { fill: colors.purple, font: { bold: true, color: "#5F497A" } } });
  statusRange.conditionalFormats.add("containsText", { text: "Conditional", format: { fill: colors.gray, font: { bold: true, color: "#404040" } } });
}

function buildListSheet(sheet, title, subtitle, data, tableName) {
  styleBase(sheet, `A1:H${Math.max(6, 5 + data.length)}`);
  addTitle(sheet, title, subtitle);
  sheet.getRange("A5:H5").values = [headers];
  sheet.getRange("A5:H5").format = {
    fill: colors.navy,
    font: { name: "Arial", size: 10, bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { bottom: { style: "medium", color: colors.navy } }
  };
  if (data.length) {
    sheet.getRange(`A6:H${5 + data.length}`).values = data;
    const body = sheet.getRange(`A6:H${5 + data.length}`);
    body.format.wrapText = true;
    body.format.borders = { bottom: { style: "thin", color: "#D9E0E6" } };
    body.format.autofitRows();
    sheet.getRange(`A6:A${5 + data.length}`).format.horizontalAlignment = "center";
    sheet.getRange(`E6:E${5 + data.length}`).format.horizontalAlignment = "center";
    applyStatusFormatting(sheet, `E6:E${5 + data.length}`);
    const table = sheet.tables.add(`A5:H${5 + data.length}`, true, tableName);
    table.style = "TableStyleMedium2";
    table.showBandedColumns = false;
    table.showFilterButton = true;
  }
  sheet.getRange("A:A").format.columnWidth = 6;
  sheet.getRange("B:B").format.columnWidth = 18;
  sheet.getRange("C:C").format.columnWidth = 34;
  sheet.getRange("D:D").format.columnWidth = 28;
  sheet.getRange("E:E").format.columnWidth = 16;
  sheet.getRange("F:F").format.columnWidth = 45;
  sheet.getRange("G:G").format.columnWidth = 33;
  sheet.getRange("H:H").format.columnWidth = 48;
  sheet.getRange("1:2").format.rowHeight = 22;
  sheet.getRange("5:5").format.rowHeight = 34;
  sheet.freezePanes.freezeRows(5);
}

styleBase(summary, "A1:C23");
addTitle(summary, "10-inch FPV drone build", "Annotated component checklist");
summary.getRange("A3:C3").values = [[`Source: ${sourceName}`,"Wishlist, ordered, and inventory entries are treated as available.",null]];
summary.getRange("A3:C3").format.font = { name: "Arial", size: 9, italic: true, color: "#52616B" };
summary.getRange("A5:C5").values = [["Cross-check status","Item count","Meaning"]];
summary.getRange("A5:C5").format = { fill: colors.navy, font: { name: "Arial", size: 10, bold: true, color: colors.white }, horizontalAlignment: "center" };
summary.getRange("A6:A10").values = statusInfo.map(x => [x[0]]);
summary.getRange("C6:C10").values = statusInfo.map(x => [x[1]]);
summary.getRange("B6").formulas = [["=COUNTIF('All Items'!$E$6:$E$40,A6)"]];
summary.getRange("B6:B10").fillDown();
summary.getRange("A11").values = [["Total"]];
summary.getRange("B11").formulas = [["=SUM(B6:B10)"]];
summary.getRange("A11:C11").format = { fill: colors.lightBlue, font: { name: "Arial", size: 10, bold: true, color: colors.navy }, borders: { top: { style: "medium", color: colors.blue } } };
summary.getRange("A14:C14").values = [["Original checklist section","Item count","Scope"]];
summary.getRange("A14:C14").format = { fill: colors.navy, font: { name: "Arial", size: 10, bold: true, color: colors.white }, horizontalAlignment: "center" };
summary.getRange("A15:A17").values = [["Required additions"],["Wiring and mounting"],["Strongly recommended"]];
summary.getRange("B15").formulas = [["=COUNTIF('All Items'!$B$6:$B$40,A15)"]];
summary.getRange("B15:B17").fillDown();
summary.getRange("C15:C17").values = [["Core parts needed to complete the 4S build"],["Connectors, protection, fasteners, and mounts"],["Setup, diagnostic, safety, and compliance items"]];
summary.getRange("A20").values = [["Cross-check basis"]];
summary.getRange("A20:C20").format = { fill: colors.lightBlue, font: { name: "Arial", size: 10, bold: true, color: colors.navy } };
summary.getRange("A21:C23").values = [
  ["Source workbook",sourceName,"Equipment Distribution!A1:D499"],
  ["Availability rule","All list types count","Current inventory, ordered, and wishlist entries were accepted as accessible."],
  ["Matching rule","Functional match","A close functional match counts as present; incomplete bundles are partial; unspecified critical attributes require verification."]
];
summary.getRange("A1:C23").format.wrapText = true;
summary.getRange("A:A").format.columnWidth = 27;
summary.getRange("B:B").format.columnWidth = 30;
summary.getRange("C:C").format.columnWidth = 68;
summary.getRange("B6:B17").format.horizontalAlignment = "center";
applyStatusFormatting(summary, "A6:A10");
summary.getRange("A1:C23").format.autofitRows();
summary.getRange("1:1").format.rowHeight = 24;
summary.getRange("2:3").format.rowHeight = 20;

buildListSheet(all,"Complete annotated checklist","Every item from the original additional-components list, with the result and source evidence from the inventory cross-check.",rows,"AllItemsTable");
buildListSheet(present,"Items represented in the spreadsheet","Reasonable matches found anywhere in the source workbook, regardless of list type.",rows.filter(r => r[4] === "Present"),"PresentItemsTable");
buildListSheet(missing,"Items not represented in the spreadsheet","No suitable entry found during the full inventory cross-check.",rows.filter(r => r[4] === "Missing"),"MissingItemsTable");
buildListSheet(partial,"Partial matches and specifications to verify","Items with incomplete bundles or possible matches that lack a critical specification.",rows.filter(r => r[4] === "Partial" || r[4] === "Verify"),"PartialVerifyTable");
buildListSheet(conditional,"Conditional item","Not listed, but needed only when the stated condition applies.",rows.filter(r => r[4] === "Conditional"),"ConditionalItemsTable");

summary.tabColor = colors.navy;
all.tabColor = colors.blue;
present.tabColor = "#70AD47";
missing.tabColor = "#C65911";
partial.tabColor = "#BF9000";
conditional.tabColor = "#7F7F7F";

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const inspection = await wb.inspect({ kind: "table", range: "All Items!A1:H40", include: "values,formulas", tableMaxRows: 40, tableMaxCols: 8, maxChars: 12000 });
console.log("INSPECTION\n" + inspection.ndjson);
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log("ERROR_SCAN\n" + errors.ndjson);

for (const sheetName of ["Summary","All Items","Present","Missing","Partial - Verify","Conditional"]) {
  const preview = await wb.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  const safeName = sheetName.replaceAll(" ", "-").toLowerCase();
  await fs.writeFile(`${previewDir}/${safeName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outputPath);
console.log(`OUTPUT ${outputPath}`);
