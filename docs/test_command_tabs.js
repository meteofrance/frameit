/* Run in a rendered task page's browser console; no test dependency required. */
(() => {
    const groups = [...document.querySelectorAll(".frameit-tabs")];
    if (!groups.length) throw Error("No command-interface groups found");
    for (const group of groups) {
        const tabs = [...group.querySelectorAll("[role=tab]")];
        const panels = [...group.querySelectorAll("[role=tabpanel]")];
        if (tabs.length !== 2 || panels.length !== 2) throw Error("Missing CLI/API tabs");
        const selected = tabs.findIndex(tab => tab.getAttribute("aria-selected") === "true");
        const focus = document.activeElement;
        tabs[1].click();
        tabs[1].focus();
        for (const [key, expected] of [["Home", 0], ["End", 1], ["ArrowRight", 0], ["ArrowLeft", 1]]) {
            document.activeElement.dispatchEvent(
                new KeyboardEvent("keydown", {key, bubbles: true, cancelable: true}));
            if (document.activeElement !== tabs[expected] || panels[expected].hidden
                    || !panels[1 - expected].hidden
                    || tabs[expected].getAttribute("aria-selected") !== "true"
                    || tabs[expected].getAttribute("aria-controls") !== panels[expected].id) {
                throw Error("Command-interface keyboard/ARIA contract failed: " + key);
            }
        }
        tabs[selected].click();
        focus.focus();
    }
    return {groupsChecked: groups.length, keyboardChecksPerGroup: 4};
})();
