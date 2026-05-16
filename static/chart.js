const chartDataElement = document.getElementById("chart-data");
const targetWeightElement = document.getElementById("target-weight");
const chartSettingsElement = document.getElementById("chart-settings");
const canvas = document.getElementById("weightChart");
let chartData = [];
let targetWeight = null;
let chartSettings = {
    lineType: "exact",
    showTargetLine: true,
};

function formatDisplayDate(dateText) {
    if (!dateText) {
        return "";
    }

    const parts = dateText.split("-");
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

document.querySelectorAll(".date-field").forEach((field) => {
    const displayInput = field.querySelector(".date-display");
    const nativeInput = field.querySelector(".native-date");
    const pickerButton = field.querySelector(".date-picker-button");

    if (!displayInput || !nativeInput || !pickerButton) {
        return;
    }

    displayInput.value = formatDisplayDate(nativeInput.value);

    nativeInput.addEventListener("change", () => {
        displayInput.value = formatDisplayDate(nativeInput.value);
    });

    function openDatePicker() {
        if (nativeInput.showPicker) {
            nativeInput.showPicker();
            return;
        }

        nativeInput.focus();
        nativeInput.click();
    }

    displayInput.addEventListener("click", openDatePicker);
    pickerButton.addEventListener("click", openDatePicker);
});

document.querySelectorAll(".entry-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
        const dateValue = form.querySelector('input[name="date"]').value;
        const weightValue = form.querySelector('input[name="weight"]').value;
        const noteValue = form.querySelector('input[name="note"]').value.trim();
        const originalDate = form.dataset.originalDate;
        const originalWeight = Number(form.dataset.originalWeight).toFixed(1);
        const originalNote = form.dataset.originalNote.trim();
        const normalizedWeight = Number(weightValue).toFixed(1);

        if (dateValue === originalDate && normalizedWeight === originalWeight && noteValue === originalNote) {
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

if (targetWeightElement) {
    const targetWeightText = targetWeightElement.content
        ? targetWeightElement.content.textContent
        : targetWeightElement.textContent;

    try {
        const parsedTargetWeight = JSON.parse(targetWeightText.trim());

        if (typeof parsedTargetWeight === "number") {
            targetWeight = parsedTargetWeight;
        }
    } catch (error) {
        targetWeight = null;
    }
}

if (chartSettingsElement) {
    const chartSettingsText = chartSettingsElement.content
        ? chartSettingsElement.content.textContent
        : chartSettingsElement.textContent;

    try {
        const parsedChartSettings = JSON.parse(chartSettingsText.trim());

        if (parsedChartSettings.lineType === "exact" || parsedChartSettings.lineType === "smoothed") {
            chartSettings.lineType = parsedChartSettings.lineType;
        }

        chartSettings.showTargetLine = parsedChartSettings.showTargetLine !== false;
    } catch (error) {
        chartSettings = {
            lineType: "exact",
            showTargetLine: true,
        };
    }
}

function buildSmoothedData(data) {
    return data.map((item, index) => {
        const start = Math.max(0, index - 6);
        const recentItems = data.slice(start, index + 1);
        const average = recentItems.reduce((sum, recentItem) => sum + recentItem.weight, 0) / recentItems.length;

        return {
            date: item.date,
            weight: average,
        };
    });
}

if (canvas && chartData.length >= 2) {
    const context = canvas.getContext("2d");

    function drawChart() {
        const lineData = chartSettings.lineType === "smoothed"
            ? buildSmoothedData(chartData)
            : chartData;
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        const pixelRatio = window.devicePixelRatio || 1;
        const padding = {
            top: 56,
            right: 26,
            bottom: 48,
            left: 76,
        };
        const weights = lineData.map((item) => item.weight);

        if (chartSettings.showTargetLine && targetWeight !== null) {
            weights.push(targetWeight);
        }

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

        if (chartSettings.showTargetLine && targetWeight !== null) {
            const targetY = getY(targetWeight);

            context.save();
            context.strokeStyle = "rgba(34, 197, 94, 0.72)";
            context.lineWidth = 2;
            context.setLineDash([8, 8]);
            context.beginPath();
            context.moveTo(padding.left, targetY);
            context.lineTo(width - padding.right, targetY);
            context.stroke();
            context.setLineDash([]);

            context.fillStyle = "#86efac";
            context.font = "bold 13px Arial, sans-serif";
            context.textAlign = "right";
            context.textBaseline = "bottom";
            context.fillText(`Tavoite ${targetWeight.toFixed(1)} kg`, width - padding.right, Math.max(targetY - 8, 18));
            context.restore();
        }

        context.shadowColor = "rgba(245, 158, 11, 0.35)";
        context.shadowBlur = 14;
        context.strokeStyle = chartSettings.lineType === "smoothed" ? "#38bdf8" : "#f6b21a";
        context.lineWidth = 3;
        context.lineJoin = "round";
        context.lineCap = "round";
        const points = lineData.map((item, index) => ({
            x: getX(index),
            y: getY(item.weight),
        }));

        context.beginPath();
        context.moveTo(points[0].x, points[0].y);

        if (chartSettings.lineType === "smoothed") {
            points.slice(1).forEach((point, index) => {
                const previousPoint = points[index];
                const middleX = (previousPoint.x + point.x) / 2;
                const middleY = (previousPoint.y + point.y) / 2;

                context.quadraticCurveTo(previousPoint.x, previousPoint.y, middleX, middleY);
            });

            const lastPoint = points[points.length - 1];
            context.lineTo(lastPoint.x, lastPoint.y);
        } else {
            points.slice(1).forEach((point) => {
                context.lineTo(point.x, point.y);
            });
        }

        context.stroke();
        context.shadowBlur = 0;

        if (chartSettings.lineType === "exact") {
            lineData.forEach((item, index) => {
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
        }

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
