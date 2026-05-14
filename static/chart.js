const chartDataElement = document.getElementById("chart-data");
const canvas = document.getElementById("weightChart");
const dateInput = document.getElementById("date");
const datePickerButton = document.querySelector(".date-picker-button");
let chartData = [];

document.querySelectorAll(".entry-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
        const dateValue = form.querySelector('input[name="date"]').value;
        const weightValue = form.querySelector('input[name="weight"]').value;
        const originalDate = form.dataset.originalDate;
        const originalWeight = Number(form.dataset.originalWeight).toFixed(1);
        const normalizedWeight = Number(weightValue).toFixed(1);

        if (dateValue === originalDate && normalizedWeight === originalWeight) {
            event.preventDefault();
            return;
        }

        if (!confirm("Tallennetaanko muutokset tähän painomerkintään?")) {
            event.preventDefault();
        }
    });
});

document.querySelectorAll(".delete-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
        if (!confirm("Haluatko varmasti poistaa tämän painomerkinnän?")) {
            event.preventDefault();
        }
    });
});

if (dateInput && datePickerButton) {
    datePickerButton.addEventListener("click", () => {
        if (dateInput.showPicker) {
            dateInput.showPicker();
            return;
        }

        dateInput.focus();
    });
}

if (chartDataElement) {
    const chartDataText = chartDataElement.content
        ? chartDataElement.content.textContent
        : chartDataElement.textContent;

    try {
        chartData = JSON.parse(chartDataText.trim());
    } catch (error) {
        chartData = [];
    }
}

if (canvas && chartData.length >= 2) {
    const context = canvas.getContext("2d");

    function drawChart() {
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        const pixelRatio = window.devicePixelRatio || 1;
        const padding = {
            top: 56,
            right: 26,
            bottom: 48,
            left: 76,
        };
        const weights = chartData.map((item) => item.weight);
        const minWeight = Math.min(...weights);
        const maxWeight = Math.max(...weights);
        const chartMin = Math.floor(minWeight) - 1;
        const chartMax = Math.ceil(maxWeight) + 1;
        const range = chartMax - chartMin || 1;
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        const yAxisValues = [];

        for (let value = chartMax; value >= chartMin; value -= 1) {
            yAxisValues.push(value);
        }

        canvas.width = width * pixelRatio;
        canvas.height = height * pixelRatio;
        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
        context.clearRect(0, 0, width, height);

        function getX(index) {
            return padding.left + (chartWidth / (chartData.length - 1)) * index;
        }

        function getY(weight) {
            return padding.top + chartHeight - ((weight - chartMin) / range) * chartHeight;
        }

        context.font = "13px Arial, sans-serif";
        context.lineWidth = 1;

        yAxisValues.forEach((value) => {
            const y = getY(value);

            context.strokeStyle = "rgba(148, 163, 184, 0.16)";
            context.beginPath();
            context.moveTo(padding.left, y);
            context.lineTo(width - padding.right, y);
            context.stroke();

            context.fillStyle = "#9aa6b8";
            context.textAlign = "right";
            context.textBaseline = "middle";
            context.fillText(`${value} kg`, padding.left - 12, y);
        });

        context.strokeStyle = "rgba(250, 204, 21, 0.28)";
        context.beginPath();
        context.moveTo(padding.left, padding.top);
        context.lineTo(padding.left, height - padding.bottom);
        context.lineTo(width - padding.right, height - padding.bottom);
        context.stroke();

        context.shadowColor = "rgba(245, 158, 11, 0.35)";
        context.shadowBlur = 14;
        context.strokeStyle = "#f6b21a";
        context.lineWidth = 3;
        context.lineJoin = "round";
        context.lineCap = "round";
        context.beginPath();

        chartData.forEach((item, index) => {
            const x = getX(index);
            const y = getY(item.weight);

            if (index === 0) {
                context.moveTo(x, y);
            } else {
                context.lineTo(x, y);
            }
        });

        context.stroke();
        context.shadowBlur = 0;

        chartData.forEach((item, index) => {
            const x = getX(index);
            const y = getY(item.weight);

            context.fillStyle = "#0b1224";
            context.strokeStyle = "#f6b21a";
            context.lineWidth = 3;
            context.beginPath();
            context.arc(x, y, 6, 0, Math.PI * 2);
            context.fill();
            context.stroke();

            context.fillStyle = "#f8fafc";
            context.font = "bold 13px Arial, sans-serif";
            context.textAlign = "center";
            context.textBaseline = "bottom";
            context.fillText(`${item.weight.toFixed(1)} kg`, x, Math.max(y - 10, 18));
        });

        context.fillStyle = "#9aa6b8";
        context.font = "13px Arial, sans-serif";
        context.textBaseline = "top";

        chartData.forEach((item, index) => {
            if (chartData.length > 6 && index % Math.ceil(chartData.length / 6) !== 0 && index !== chartData.length - 1) {
                return;
            }

            const x = getX(index);
            context.textAlign = "center";
            context.fillText(formatDate(item.date), x, height - padding.bottom + 16);
        });
    }

    function formatDate(dateText) {
        const parts = dateText.split("-");
        return `${parts[2]}.${parts[1]}`;
    }

    drawChart();
    window.addEventListener("resize", drawChart);
}
