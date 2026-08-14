const encoder = new TextEncoder();
const decoder = new TextDecoder();
const status = document.querySelector("#status");
const form = document.querySelector("#provision-form");

function endpointId(name) {
  const slug = name.toLowerCase().normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 39);
  // A 96-bit random suffix keeps identities collision-resistant even when many
  // users choose the same friendly name, while remaining within the firmware's
  // 64-character endpoint ID limit.
  const random = crypto.getRandomValues(new Uint8Array(12));
  const suffix = [...random].map(value => value.toString(16).padStart(2, "0")).join("");
  return `${slug || "roomhub"}-${suffix}`;
}

async function writeLine(writer, value) {
  await writer.write(encoder.encode(`${value}\n`));
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (!("serial" in navigator)) {
    status.textContent = "Web Serial is unavailable. Use Chrome or Edge on a desktop computer.";
    return;
  }

  let port;
  let reader;
  let writer;
  try {
    status.textContent = "Select the Tab5 serial port…";
    port = await navigator.serial.requestPort();
    await port.open({ baudRate: 115200 });
    reader = port.readable.getReader();
    writer = port.writable.getWriter();

    const fields = {
      endpoint_id: endpointId(document.querySelector("#endpoint-name").value),
      roomhub_url: document.querySelector("#roomhub-url").value.replace(/\/$/, ""),
      device_token: document.querySelector("#device-token").value,
      wifi_ssid: document.querySelector("#wifi-ssid").value,
      wifi_password: document.querySelector("#wifi-password").value,
    };
    await writeLine(writer, "ROOMHUB_PROVISION 1");
    status.textContent = "Configuring the Tab5…";

    let pending = "";
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      let newline;
      while ((newline = pending.indexOf("\n")) >= 0) {
        const line = pending.slice(0, newline).trim();
        pending = pending.slice(newline + 1);
        if (line.startsWith("ROOMHUB_FIELD ")) {
          const field = line.slice("ROOMHUB_FIELD ".length);
          if (!(field in fields)) throw new Error(`Device requested unknown field: ${field}`);
          await writeLine(writer, fields[field]);
          if (field === "wifi_password") fields.wifi_password = "";
          if (field === "device_token") fields.device_token = "";
        } else if (line === "ROOMHUB_RESULT saved") {
          form.reset();
          status.textContent = "Configuration saved. The Tab5 is restarting and will appear in RoomHub.";
          return;
        } else if (line.startsWith("ROOMHUB_RESULT ")) {
          throw new Error(`Provisioning failed: ${line.slice("ROOMHUB_RESULT ".length)}`);
        }
      }
    }
    throw new Error("The Tab5 did not respond within 30 seconds. Reset it and try again.");
  } catch (error) {
    status.textContent = error.message;
  } finally {
    if (reader) reader.releaseLock();
    if (writer) writer.releaseLock();
    if (port?.readable || port?.writable) await port.close();
  }
});
