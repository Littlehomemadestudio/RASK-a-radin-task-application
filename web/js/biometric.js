// biometric.js — App lock with WebAuthn + PIN.
window.RaskLock = (function () {
  // === Lock mode ===
  async function getMode() { return await window.RaskDB.kvGet("lock_mode", "none"); }
  async function setMode(m) { return await window.RaskDB.kvSet("lock_mode", m); }
  async function clear() {
    await window.RaskDB.kvSet("lock_mode", "none");
    await window.RaskDB.kvSet("pin_hash", "");
    await window.RaskDB.kvSet("pin_salt", "");
    await window.RaskDB.kvSet("webauthn_cred_id", "");
  }

  // === PIN ===
  async function hashPin(pin, salt) {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw", enc.encode(pin), "PBKDF2", false, ["deriveBits"]
    );
    const bits = await crypto.subtle.deriveBits(
      { name: "PBKDF2", salt, iterations: 200000, hash: "SHA-256" },
      key, 256
    );
    return new Uint8Array(bits);
  }
  function bytesToHex(b) {
    return Array.from(b).map((x) => x.toString(16).padStart(2, "0")).join("");
  }
  function hexToBytes(h) {
    const out = new Uint8Array(h.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(h.slice(i*2, i*2+2), 16);
    return out;
  }
  async function setupPin(pin) {
    if (pin.length < 4) throw new Error("PIN too short");
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const hash = await hashPin(pin, salt);
    await window.RaskDB.kvSet("pin_salt", bytesToHex(salt));
    await window.RaskDB.kvSet("pin_hash", bytesToHex(hash));
    await setMode("pin");
  }
  async function verifyPin(pin) {
    const saltHex = await window.RaskDB.kvGet("pin_salt", "");
    const hashHex = await window.RaskDB.kvGet("pin_hash", "");
    if (!saltHex || !hashHex) return false;
    const salt = hexToBytes(saltHex);
    const expected = hexToBytes(hashHex);
    const actual = await hashPin(pin, salt);
    if (actual.length !== expected.length) return false;
    let diff = 0;
    for (let i = 0; i < actual.length; i++) diff |= actual[i] ^ expected[i];
    return diff === 0;
  }

  // === WebAuthn (biometric) ===
  function webauthnAvailable() {
    return window.PublicKeyCredential !== undefined &&
           typeof window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable === "function";
  }
  async function isBiometricAvailable() {
    if (!webauthnAvailable()) return false;
    try {
      return await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
    } catch (_) { return false; }
  }
  function bufToBase64(buf) {
    const arr = new Uint8Array(buf);
    let str = "";
    for (let i = 0; i < arr.length; i++) str += String.fromCharCode(arr[i]);
    return btoa(str);
  }
  function base64ToBuf(b64) {
    const str = atob(b64);
    const out = new Uint8Array(str.length);
    for (let i = 0; i < str.length; i++) out[i] = str.charCodeAt(i);
    return out.buffer;
  }
  async function setupBiometric() {
    if (!(await isBiometricAvailable())) throw new Error("Biometric unavailable");
    const challenge = crypto.getRandomValues(new Uint8Array(32));
    const userId = crypto.getRandomValues(new Uint8Array(16));
    const cred = await navigator.credentials.create({
      publicKey: {
        challenge,
        rp: { name: "Rask" },
        user: { id: userId, name: "rask-user", displayName: "Rask User" },
        pubKeyCredParams: [
          { type: "public-key", alg: -7 },      // ES256
          { type: "public-key", alg: -257 },    // RS256
        ],
        authenticatorSelection: {
          authenticatorAttachment: "platform",
          userVerification: "required",
          residentKey: "preferred",
        },
        timeout: 60000,
      }
    });
    if (!cred) throw new Error("Biometric setup failed");
    await window.RaskDB.kvSet("webauthn_cred_id", bufToBase64(cred.rawId));
    await setMode("biometric");
  }
  async function authenticateBiometric() {
    const credIdB64 = await window.RaskDB.kvGet("webauthn_cred_id", "");
    if (!credIdB64) throw new Error("No biometric credential stored");
    const challenge = crypto.getRandomValues(new Uint8Array(32));
    const cred = await navigator.credentials.get({
      publicKey: {
        challenge,
        allowCredentials: [{
          id: base64ToBuf(credIdB64),
          type: "public-key",
          transports: ["internal"],
        }],
        userVerification: "required",
        timeout: 60000,
      }
    });
    return !!cred;
  }

  return {
    getMode, setMode, clear,
    setupPin, verifyPin,
    isBiometricAvailable, setupBiometric, authenticateBiometric,
    webauthnAvailable,
  };
})();
