from test_open_deskos_package import report


def test_configured_transitions_keep_diagnostics_command_only() -> None:
    result = report(r'''
        import net from "node:net";
        const peers = [];
        const records = [];
        const server = net.createServer((socket) => {
          peers.push(socket);
          let pending = "";
          socket.on("data", (chunk) => {
            pending += chunk.toString();
            const lines = pending.split("\n");
            pending = lines.pop();
            for (const line of lines) if (line) records.push(JSON.parse(line));
          });
        });
        await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
        process.env.ODK_DESK_LINK_ADDRESS = `127.0.0.1:${server.address().port}`;
        process.env.ODK_DESK_LINK_TOKEN = "local-test";
        process.env.ODK_DESK_LINK_MACHINE = "diagnostic-probe";
        const { default: extension } = await import("./packages/open-deskos/index.ts");
        const handlers = new Map(), commands = new Map();
        const statuses = [], footers = [], notices = [];
        extension({
          on(name, handler) { handlers.set(name, handler); },
          registerCommand(name, command) { commands.set(name, command); },
        });
        const ctx = {
          cwd: "/w/probe",
          isIdle: () => true,
          sessionManager: { getSessionId: () => "probe", getSessionName: () => "Probe", getHeader: () => undefined },
          ui: {
            setStatus(...args) { statuses.push(args); },
            setFooter(...args) { footers.push(args); },
            notify(...args) { notices.push(args); },
          },
        };
        const diagnose = () => commands.get("open-deskos").handler("", ctx);
        async function waitFor(condition) {
          const deadline = Date.now() + 4000;
          while (!condition()) {
            if (Date.now() > deadline) throw new Error("local transition timed out");
            await new Promise((resolve) => setTimeout(resolve, 10));
          }
        }
        try {
          handlers.get("session_start")({}, ctx);
          await diagnose();
          await waitFor(() => records.some((r) => r.type === "hello"));
          handlers.get("message_end")({ message: { role: "user", content: "local goal" } }, ctx);
          handlers.get("agent_settled")({}, ctx);
          await diagnose();
          await waitFor(() => records.some((r) => r.type === "events"));
          peers[0].destroy();
          // The socket-close callback runs asynchronously while the session is idle.
          await waitFor(() => peers[0].destroyed);
          await new Promise((resolve) => setTimeout(resolve, 100));
          await diagnose();
          await waitFor(() => records.filter((r) => r.type === "hello").length === 2);
          await diagnose();
          handlers.get("session_shutdown")({}, ctx);
          await diagnose();
          console.log(JSON.stringify({ statuses, footers, notices, records }));
        } finally {
          handlers.get("session_shutdown")({}, ctx);
          for (const peer of peers) peer.destroy();
          await new Promise((resolve) => server.close(resolve));
        }
    ''')
    assert result["statuses"] == [], "no status writes, including clears, on any transition"
    assert result["footers"] == [], "no replacement footer"
    notices = result["notices"]
    assert len(notices) == 5, "only explicit commands emit diagnostics"
    for notice, state in zip(notices, ["connecting", "connected", "offline", "connected", "offline"]):
        assert f"[open-deskos] {state}" in notice[0]
        assert "diagnostic-probe" in notice[0]
        assert "1 session(s)" in notice[0]
    assert "1 event(s)" in notices[1][0]
    assert any(record["type"] == "events" for record in result["records"])
