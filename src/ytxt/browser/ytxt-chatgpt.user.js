// ==UserScript==
// @name         ytxt ChatGPT draft helper
// @namespace    ytxt
// @version      0.4.0
// @description  Prefill ytxt drafts and select transcript files. Never submits a message.
// @match        https://chatgpt.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-idle
// @noframes
// ==/UserScript==

(async () => {
    "use strict";
    if (location.origin !== "https://chatgpt.com" || location.pathname !== "/"
        || !location.hash.startsWith("#ytxt=")) return;

    const params = new URLSearchParams(location.hash.slice(6));
    const port = Number(params.get("port"));
    const token = params.get("token") || "";
    if (!Number.isInteger(port) || port < 1024 || port > 65535
        || !/^[A-Za-z0-9_-]{43}$/.test(token)) return;

    history.replaceState(null, "", location.pathname + location.search);
    const endpoint = "http://127.0.0.1:" + port;
    const request = (path, data) => new Promise((resolve, reject) => {
        GM_xmlhttpRequest({
            method: data ? "POST" : "GET",
            url: endpoint + path,
            anonymous: true,
            headers: {
                "Authorization": "Bearer " + token,
                ...(data ? {"Content-Type": "application/json"} : {}),
            },
            data: data ? JSON.stringify(data) : undefined,
            timeout: 10000,
            onload: response => {
                if (response.status !== 200) {
                    reject(new Error("ytxt bridge returned " + response.status));
                    return;
                }
                try { resolve(JSON.parse(response.responseText)); }
                catch { reject(new Error("Invalid ytxt bridge response")); }
            },
            onerror: () => reject(new Error("Cannot reach ytxt. Rerun the command in your terminal.")),
            ontimeout: () => reject(new Error("The ytxt connection timed out.")),
        });
    });

    const notice = message => {
        let banner = document.getElementById("ytxt-draft-status");
        if (!banner) {
            banner = document.createElement("div");
            banner.id = "ytxt-draft-status";
            banner.setAttribute("role", "status");
            banner.style.cssText = "position:fixed;top:12px;right:12px;z-index:2147483647;"
                + "max-width:440px;padding:14px;background:#17352a;color:white;"
                + "border:1px solid #69aa85;border-radius:8px;font:14px sans-serif";
            document.body.append(banner);
        }
        banner.textContent = "ytxt: " + message;
    };

    const waitFor = async find => {
        const deadline = Date.now() + 150000;
        while (Date.now() < deadline) {
            const found = find();
            if (found) return found;
            await new Promise(resolve => setTimeout(resolve, 250));
        }
        throw new Error("ChatGPT's composer or file input was unavailable. Sign in, then retry.");
    };

    try {
        notice("Loading transcript draft…");
        const draft = await request("/draft");
        if (typeof draft.prompt !== "string" || !Array.isArray(draft.files) || !draft.files.length) {
            throw new Error("Invalid draft");
        }
        const editor = await waitFor(() => document.querySelector(
            '#prompt-textarea[contenteditable="true"], textarea#prompt-textarea'
        ));
        const currentText = () => editor.tagName === "TEXTAREA" ? editor.value : editor.textContent;
        if (currentText().trim()) {
            throw new Error("An existing ChatGPT draft is present. Clear it or save it, then rerun ytxt.");
        }

        // Select a general document input, avoiding image-only controls.
        const input = await waitFor(() => Array.from(document.querySelectorAll('input[type="file"]'))
            .find(element => {
                const accept = (element.getAttribute("accept") || "").toLowerCase();
                return !element.disabled && (!accept || accept === "*"
                    || accept.includes(".txt") || accept.includes("text/"));
            }));
        if (input.files && input.files.length) {
            throw new Error("The composer already contains files. Start an empty chat and rerun ytxt.");
        }
        if (document.querySelector('button[aria-label^="Remove file"], button[aria-label^="Remove attachment"]')) {
            throw new Error("The composer already has attachments. Start an empty chat and rerun ytxt.");
        }
        if (draft.files.length > 1 && !input.multiple) {
            throw new Error("This file input accepts only one file. Use ytxt --combine and retry.");
        }
        // Recheck immediately before modifying the draft after waiting for controls.
        if (currentText().trim()) {
            throw new Error("The ChatGPT draft changed. Your text has been preserved; rerun ytxt.");
        }

        const transfer = new DataTransfer();
        for (const attachment of draft.files) {
            if (typeof attachment.name !== "string" || typeof attachment.data !== "string") {
                throw new Error("Invalid transcript attachment");
            }
            const bytes = Uint8Array.from(atob(attachment.data), character => character.charCodeAt(0));
            transfer.items.add(new File([bytes], attachment.name, {type: "text/plain"}));
        }

        editor.focus();
        if (editor.tagName === "TEXTAREA") {
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(editor, draft.prompt);
            editor.dispatchEvent(new Event("input", {bubbles: true}));
        } else {
            const range = document.createRange();
            range.selectNodeContents(editor);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            if (!document.execCommand("insertText", false, draft.prompt)) {
                throw new Error("Cannot insert text into this composer. Your saved prompt is available in ytxt's draft folder.");
            }
        }

        input.files = transfer.files;
        input.dispatchEvent(new Event("change", {bubbles: true}));
        editor.focus();
        notice("Draft prepared. Review the files, wait for uploads, and add your question before sending.");
        await request("/status", {state: "prepared"});
    } catch (error) {
        const message = String(error.message || error).slice(0, 1000);
        notice(message);
        try { await request("/status", {state: "error", message}); }
        catch { /* The local bridge may have expired; the on-page notice remains. */ }
    }
})();
