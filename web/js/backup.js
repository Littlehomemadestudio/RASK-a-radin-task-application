// backup.js — Encrypted backup/restore using Web Crypto API.
// Format (binary):
//   [magic:4]  "RASK"
//   [ver:1]    1
//   [salt:16]
//   [iv:12]    (AES-GCM standard 12-byte IV)
//   [ct_len:4]
//   [ciphertext:N]
// Key: PBKDF2-SHA256, 200k iterations, 32 bytes.
// Cipher: AES-256-GCM (authenticated).
window.RaskBackup = (function () {
  const MAGIC = new Uint8Array([0x52, 0x41, 0x53, 0x4B]); // "RASK"
  const VERSION = 1;
  const KDF_ITER = 200000;
  const SALT_LEN = 16;
  const IV_LEN = 12;

  async function deriveKey(password, salt) {
    const enc = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
      "raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]
    );
    return crypto.subtle.deriveKey(
      { name: "PBKDF2", salt, iterations: KDF_ITER, hash: "SHA-256" },
      keyMaterial,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  }

  function concatBytes(...arrs) {
    const total = arrs.reduce((s, a) => s + a.length, 0);
    const out = new Uint8Array(total);
    let off = 0;
    for (const a of arrs) { out.set(a, off); off += a.length; }
    return out;
  }

  async function exportToBytes(password) {
    const payload = await window.RaskDB.exportAll();
    payload._meta = {
      version: VERSION,
      app_version: "1.0.0",
      exported_at: new Date().toISOString(),
    };
    const json = JSON.stringify(payload);
    const enc = new TextEncoder();
    const plaintext = enc.encode(json);
    const salt = crypto.getRandomValues(new Uint8Array(SALT_LEN));
    const iv = crypto.getRandomValues(new Uint8Array(IV_LEN));
    const key = await deriveKey(password, salt);
    const ct = new Uint8Array(await crypto.subtle.encrypt(
      { name: "AES-GCM", iv }, key, plaintext
    ));
    // Pack
    const lenBytes = new Uint8Array(4);
    new DataView(lenBytes.buffer).setUint32(0, ct.length, false);
    return concatBytes(MAGIC, new Uint8Array([VERSION]), salt, iv, lenBytes, ct);
  }

  async function importFromBytes(bytes, password) {
    bytes = new Uint8Array(bytes);
    // Validate magic
    for (let i = 0; i < 4; i++) {
      if (bytes[i] !== MAGIC[i]) throw new Error("Not a Rask backup file (bad magic).");
    }
    let off = 4;
    const ver = bytes[off]; off += 1;
    if (ver !== VERSION) throw new Error(`Unsupported backup version ${ver}.`);
    const salt = bytes.slice(off, off + SALT_LEN); off += SALT_LEN;
    const iv = bytes.slice(off, off + IV_LEN); off += IV_LEN;
    const len = new DataView(bytes.buffer, bytes.byteOffset + off, 4).getUint32(0, false);
    off += 4;
    const ct = bytes.slice(off, off + len);
    const key = await deriveKey(password, salt);
    let plaintext;
    try {
      plaintext = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
    } catch (_) {
      throw new Error("Wrong password or corrupted file.");
    }
    const json = new TextDecoder().decode(plaintext);
    const payload = JSON.parse(json);
    if (!payload || !payload.activities) throw new Error("Invalid backup payload.");
    await window.RaskDB.replaceAll(payload);
    return payload;
  }

  async function exportToFile(filename, password) {
    const bytes = await exportToBytes(password);
    const blob = new Blob([bytes], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || `rask_backup_${new Date().toISOString().replace(/[:.]/g, "-")}.rask`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function pickFile() {
    return new Promise((resolve, reject) => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".rask,application/octet-stream";
      input.onchange = () => {
        const f = input.files[0];
        if (!f) return resolve(null);
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error);
        reader.readAsArrayBuffer(f);
      };
      input.click();
    });
  }

  async function importFromFile(password) {
    const buf = await pickFile();
    if (!buf) return false;
    await importFromBytes(buf, password);
    return true;
  }

  return { exportToBytes, importFromBytes, exportToFile, importFromFile, pickFile };
})();
