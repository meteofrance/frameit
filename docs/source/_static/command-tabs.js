document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".frameit-tabs").forEach((group, groupIndex) => {
        const panels = Array.from(group.querySelectorAll(":scope > .frameit-tab"));
        if (panels.length < 2) return;
        const list = document.createElement("div");
        list.className = "frameit-tablist";
        list.setAttribute("role", "tablist");
        list.setAttribute("aria-label", "Command interface");
        const buttons = panels.map((panel, index) => {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = panel.querySelector(".rubric").textContent;
            button.id = `command-tab-${groupIndex}-${index}`;
            panel.id = `command-panel-${groupIndex}-${index}`;
            button.setAttribute("role", "tab");
            button.setAttribute("aria-controls", panel.id);
            panel.setAttribute("role", "tabpanel");
            panel.setAttribute("aria-labelledby", button.id);
            panel.tabIndex = 0;
            list.append(button);
            return button;
        });
        const select = (index) => {
            buttons.forEach((button, position) => {
                button.setAttribute("aria-selected", String(position === index));
                button.tabIndex = position === index ? 0 : -1;
                panels[position].hidden = position !== index;
            });
        };
        buttons.forEach((button, index) => {
            button.addEventListener("click", () => select(index));
            button.addEventListener("keydown", (event) => {
                let next;
                if (event.key === "ArrowRight") next = (index + 1) % buttons.length;
                else if (event.key === "ArrowLeft") next = (index + buttons.length - 1) % buttons.length;
                else if (event.key === "Home") next = 0;
                else if (event.key === "End") next = buttons.length - 1;
                else return;
                event.preventDefault();
                select(next);
                buttons[next].focus();
            });
        });
        group.prepend(list);
        group.classList.add("frameit-tabs-ready");
        select(0);
    });
});
