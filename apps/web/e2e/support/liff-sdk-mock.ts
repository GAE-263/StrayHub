type Scenario = "supported" | "unavailable" | "send-fails" | "close-fails";

const scenario = (): Scenario =>
  (window.sessionStorage.getItem("liff_handoff_scenario") as Scenario | null) ??
  "unavailable";

const increment = (key: string) => {
  const current = Number(window.sessionStorage.getItem(key) ?? "0");
  window.sessionStorage.setItem(key, String(current + 1));
};

const liff = {
  get id() {
    return scenario() === "unavailable" ? null : "playwright-liff-id";
  },
  isInClient() {
    return scenario() !== "unavailable";
  },
  isApiAvailable() {
    return false;
  },
  permission: {
    async query() {
      return {
        state: scenario() === "unavailable" ? "unavailable" : "granted",
      };
    },
  },
  async sendMessages(messages: unknown[]) {
    increment("liff_handoff_send_count");
    window.sessionStorage.setItem(
      "liff_handoff_messages",
      JSON.stringify(messages),
    );
    if (scenario() === "send-fails") throw new Error("mock send failure");
  },
  closeWindow() {
    increment("liff_handoff_close_count");
    if (scenario() === "close-fails") throw new Error("mock close failure");
  },
};

export default liff;
