const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {test} = require("node:test");
const source = fs.readFileSync("src/ytxt/browser/ytxt-chatgpt.user.js", "utf8");

async function simulate(options = {}) {
    const calls = [];
    const events = [];
    const notices = [];
    const editor = {
        tagName: options.contenteditable ? "DIV" : "TEXTAREA",
        value: options.existing || "",
        textContent: options.existing || "",
        focus() {},
        dispatchEvent(event) { events.push(event.type); },
    };
    const input = {
        disabled: false, multiple: true, files: [],
        getAttribute() { return ""; },
        dispatchEvent(event) { events.push(event.type); },
    };
    const banner = {set textContent(value) { notices.push(value); }};
    class Textarea {}
    Object.defineProperty(Textarea.prototype, "value", {
        set(value) { this.value = value; },
    });
    const context = {
        URLSearchParams, Uint8Array,
        location: {
            origin: options.origin || "https://chatgpt.com",
            pathname: options.pathname || "/",
            search: "",
            hash: "#ytxt=port=12345&token=" + "a".repeat(43),
        },
        history: {replaceState() { calls.push("remove-fragment"); }},
        document: {
            querySelector(selector) {
                return selector.includes("#prompt-textarea") ? editor : null;
            },
            querySelectorAll() { return [input]; },
            getElementById() { return banner; },
            createRange() { return {selectNodeContents() {}}; },
            execCommand(command, ui, text) {
                calls.push(command);
                editor.textContent = text;
                return true;
            },
        },
        window: {getSelection() { return {removeAllRanges() {}, addRange() {}}; }},
        Event: class { constructor(type) { this.type = type; } },
        HTMLTextAreaElement: Textarea,
        DataTransfer: class {
            constructor() {
                this.files = [];
                this.items = {add: file => this.files.push(file)};
            }
        },
        File: class {
            constructor(parts, name, attributes) {
                this.parts = parts; this.name = name; this.type = attributes.type;
            }
        },
        atob: data => Buffer.from(data, "base64").toString("binary"),
        Date, setTimeout,
        GM_xmlhttpRequest(request) {
            calls.push(request);
            if (request.url.endsWith("/draft")) {
                request.onload({status: 200, responseText: JSON.stringify({
                    prompt: "Discuss <claims> & evidence.\nI will add my question.",
                    files: [{name: "café.txt", data: Buffer.from("Original café").toString("base64")}],
                })});
            } else {
                request.onload({status: 200, responseText: "{}"});
            }
        },
    };
    await vm.runInNewContext(source, context);
    return {calls, events, notices, editor, input};
}

test("prefills textarea and supplies actual file bytes without a send action", async () => {
    const result = await simulate();
    assert.match(result.editor.value, /Discuss <claims> & evidence/);
    assert.equal(result.input.files[0].name, "café.txt");
    assert.equal(Buffer.from(result.input.files[0].parts[0]).toString("utf8"), "Original café");
    assert.deepEqual(result.events, ["input", "change"]);
    const status = result.calls.find(call => call.url?.endsWith("/status"));
    assert.equal(JSON.parse(status.data).state, "prepared");
    assert.equal(status.headers.Authorization, "Bearer " + "a".repeat(43));
    assert.ok(!result.events.includes("submit"));
});

test("uses text insertion for contenteditable composer", async () => {
    const result = await simulate({contenteditable: true});
    assert.ok(result.calls.includes("insertText"));
    assert.match(result.editor.textContent, /Discuss <claims>/);
    assert.equal(result.input.files.length, 1);
});

test("preserves an existing unsent draft", async () => {
    const result = await simulate({existing: "My unsent question"});
    assert.equal(result.editor.value, "My unsent question");
    assert.equal(result.input.files.length, 0);
    const status = result.calls.find(call => call.url?.endsWith("/status"));
    assert.equal(JSON.parse(status.data).state, "error");
    assert.match(JSON.parse(status.data).message, /existing ChatGPT draft/);
    assert.deepEqual(result.events, []);
});

test("does nothing outside ChatGPT's new-chat page", async () => {
    for (const options of [{origin: "https://evil.example"}, {pathname: "/c/existing-chat"}]) {
        const result = await simulate(options);
        assert.deepEqual(result.calls, []);
    }
});
