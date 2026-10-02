import fs from "node:fs";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("Usage: node convert-intel-hex.mjs input.hex output.bin");
}

let upperAddress = 0;
let minimumAddress = Number.POSITIVE_INFINITY;
let maximumAddress = -1;
const chunks = [];

for (const [lineNumber, rawLine] of fs.readFileSync(inputPath, "utf8").split(/\r?\n/).entries()) {
  const line = rawLine.trim();
  if (!line) continue;
  if (!line.startsWith(":")) throw new Error(`Invalid HEX record at line ${lineNumber + 1}`);
  const record = Buffer.from(line.slice(1), "hex");
  if (record.length < 5 || record[0] + 5 !== record.length) {
    throw new Error(`Invalid record length at line ${lineNumber + 1}`);
  }
  if ((record.reduce((sum, value) => sum + value, 0) & 0xff) !== 0) {
    throw new Error(`Checksum failure at line ${lineNumber + 1}`);
  }
  const byteCount = record[0];
  const offset = record.readUInt16BE(1);
  const type = record[3];
  const data = record.subarray(4, 4 + byteCount);

  if (type === 0x00) {
    const address = upperAddress + offset;
    chunks.push({ address, data: Buffer.from(data) });
    minimumAddress = Math.min(minimumAddress, address);
    maximumAddress = Math.max(maximumAddress, address + data.length - 1);
  } else if (type === 0x04) {
    if (data.length !== 2) throw new Error(`Invalid extended address at line ${lineNumber + 1}`);
    upperAddress = data.readUInt16BE(0) << 16;
  } else if (type === 0x02) {
    if (data.length !== 2) throw new Error(`Invalid segment address at line ${lineNumber + 1}`);
    upperAddress = data.readUInt16BE(0) << 4;
  } else if (type === 0x01) {
    break;
  } else if (type !== 0x03 && type !== 0x05) {
    throw new Error(`Unsupported record type ${type} at line ${lineNumber + 1}`);
  }
}

if (minimumAddress !== 0x08000000 || maximumAddress >= 0x08200000) {
  throw new Error(`Unexpected STM32F7 address range: 0x${minimumAddress.toString(16)}-0x${maximumAddress.toString(16)}`);
}

const image = Buffer.alloc(maximumAddress - minimumAddress + 1, 0xff);
for (const chunk of chunks) chunk.data.copy(image, chunk.address - minimumAddress);
fs.writeFileSync(outputPath, image);
console.log(`Converted 0x${minimumAddress.toString(16)}-0x${maximumAddress.toString(16)} (${image.length} bytes)`);
