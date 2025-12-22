
document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("patient-search");
    const dropdown = document.getElementById("autocomplete-results");
    let timeout = null;

    input.addEventListener("input", function () {
        clearTimeout(timeout);
        const query = this.value.trim();

        if (query.length < 2) {
            dropdown.classList.add("hidden");
            return;
        }

        timeout = setTimeout(() => {
            fetch(`/clinician/patients/autocomplete/?q=${query}`)
                .then(res => res.json())
                .then(data => {
                    dropdown.innerHTML = "";

                    if (!data.results.length) {
                        dropdown.classList.add("hidden");
                        return;
                    }

                    data.results.forEach(item => {
                        const div = document.createElement("div");
                        div.className =
                            "px-4 py-2 hover:bg-gray-100 cursor-pointer";

                        div.innerHTML = `
                            <strong>${item.name}</strong><br>
                            <span class="text-xs text-gray-500">
                                ${item.patient_id} • ${item.email || ""}
                            </span>
                        `;

                        div.onclick = () => {
                            window.location.href =
                                `/clinician/patients/${item.patient_id}/`;
                        };

                        dropdown.appendChild(div);
                    });

                    dropdown.classList.remove("hidden");
                });
        }, 300);
    });

    document.addEventListener("click", function (e) {
        if (!dropdown.contains(e.target) && e.target !== input) {
            dropdown.classList.add("hidden");
        }
    });
});
