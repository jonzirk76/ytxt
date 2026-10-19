const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {test} = require("node:test");
const source = fs.readFileSync("src/ytxt/browser/ytxt-chatgpt.user.js", "utf8");

async function simulate(options = {}) {
    const calls = [];
    const events = [];
    const notices = [];
    let now = 0;
    let menuOpened = false;
    const editor = {
        tagName: options.contenteditable ? "DIV" : "TEXTAREA",
        value: options.existing || "",
        textContent: options.existing || "",
        getAttribute() { return null; },
        getClientRects() { return [{}]; },
        focus() {},
        dispatchEvent(event) { events.push(event.type); },
    };
    const input = {
        disabled: false, multiple: true, files: [],
        getAttribute(name) { return name === "accept" ? (options.accept || "") : null; },
        dispatchEvent(event) { events.push(event.type); },
    };
    const menu = {
        disabled: false,
        getAttribute(name) {
            return {"data-testid": "composer-plus-btn", "aria-expanded": String(menuOpened)}[name] || null;
        },
        getClientRects() { return [{}]; },
        click() { calls.push("attachment-menu"); menuOpened = true; },
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
            querySelector() { return null; },
            querySelectorAll(selector) {
                if (selector === 'input[type="file"]') {
                    if (options.noInput || (options.lazyInput && !menuOpened)) return [];
                    return [input];
                }
                if (selector.includes("composer-plus-btn")) return options.lazyInput ? [menu] : [];
                if (options.noEditor) return [];
                const editorSelector = options.editorSelector || (options.contenteditable
                    ? '#prompt-textarea[contenteditable]:not([contenteditable="false"])'
                    : 'textarea#prompt-textarea');
                return selector === editorSelector ? [editor] : [];
            },
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
        Date: {now: () => now},
        setTimeout(callback, milliseconds) { now += milliseconds; callback(); },
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

test("finds a rich-text editor inside a wrapper or with a different ID", async () => {
    for (const editorSelector of [
        '#prompt-textarea [contenteditable]:not([contenteditable="false"])',
        'form .ProseMirror[contenteditable="true"]',
        'form [role="textbox"][contenteditable]:not([contenteditable="false"])',
    ]) {
        const result = await simulate({contenteditable: true, editorSelector});
        assert.match(result.editor.textContent, /Discuss <claims>/);
        assert.equal(result.input.files.length, 1);
    }
});

test("accepts an all-files upload control", async () => {
    for (const accept of ["*/*", "*", ".pdf, .TXT", "text/plain", "text/*"]) {
        const result = await simulate({accept});
        assert.equal(result.input.files.length, 1, accept);
    }
});

test("opens the attachment menu when the file input is mounted lazily", async () => {
    const result = await simulate({lazyInput: true});
    assert.deepEqual(result.calls.filter(call => call === "attachment-menu"), ["attachment-menu"]);
    assert.equal(result.input.files.length, 1);
    assert.ok(!result.events.includes("submit"));
});

test("does not open attachment controls for an existing unsent draft", async () => {
    const result = await simulate({lazyInput: true, existing: "Keep this"});
    assert.ok(!result.calls.includes("attachment-menu"));
    assert.equal(result.editor.value, "Keep this");
});

test("identifies missing editor separately from missing upload controls", async () => {
    for (const options of [{noEditor: true}, {noInput: true}, {accept: "image/*"}]) {
        const result = await simulate(options);
        const status = JSON.parse(result.calls.find(call => call.url?.endsWith("/status")).data);
        assert.equal(status.state, "error");
        assert.match(status.message, options.noEditor ? /editable message box/ : /no file input accepting/);
        assert.doesNotMatch(status.message, /Sign in, then retry/);
        assert.equal(result.editor.value, "");
        assert.deepEqual(result.events, []);
    }
});
