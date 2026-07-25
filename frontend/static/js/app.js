/**
 * Протоколы разногласий: выбор службы, загрузка договора, обработка, результат, экспорт в Word.
 */
const API = {
    async getServices() {
        const r = await fetch("/api/prompts");
        if (!r.ok) throw new Error("Не удалось загрузить список служб");
        const data = await r.json();
        return data.services || [];
    },
    async processDocument(file, promptId) {
        const form = new FormData();
        form.append("file", file);
        form.append("prompt_id", promptId);
        const r = await fetch("/api/process", { method: "POST", body: form });
        if (!r.ok) {
            const err = await r.json().catch(() => ({}));
            throw new Error(err.detail || `Ошибка ${r.status}`);
        }
        return r.json();
    },
    async getStatus(requestId) {
        const r = await fetch(`/api/status/${requestId}`);
        if (!r.ok) return null;
        return r.json();
    },
    async getResult(requestId) {
        const r = await fetch(`/api/result/${requestId}`);
        if (!r.ok) throw new Error("Результат не найден");
        return r.json();
    },
    async exportWord(protocolText, letterText, filename, part = "both") {
        const r = await fetch("/api/export-word", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                protocol_text: protocolText,
                letter_text: letterText,
                filename: filename || "protocol",
                part: part,
            }),
        });
        if (!r.ok) throw new Error("Ошибка экспорта");
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const ext = part === "protocol" ? "_протокол.docx" : part === "letter" ? "_письмо.docx" : ".docx";
        a.download = (filename || "protocol") + ext;
        a.click();
        URL.revokeObjectURL(url);
    },
};

const POLL_INTERVAL = 1500; // Более частое обновление для плавности
const STATUS_PHASES = {
    'processing': { color: '#4b5563' },
    'ocr': { color: '#4b5563' },
    'ocr_queued': { color: '#4b5563' },
    'masking': { color: '#4b5563' },
    'analysis': { color: '#4b5563' },
    'unmasking': { color: '#4b5563' },
    'complete': { color: '#10b981' },
    'error': { color: '#ef4444' }
};

const STATUS_MESSAGES = {
    'processing': 'Обработка',
    'ocr': 'Распознавание страниц',
    'ocr_queued': 'Запрос в очереди...',
    'masking': 'Маскировка данных',
    'analysis': 'Формируем протокол разногласий и сопроводительное письмо',
    'unmasking': 'Восстановление данных',
    'complete': 'Готово',
    'error': 'Ошибка'
};

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " Б";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " КБ";
    return (bytes / (1024 * 1024)).toFixed(1) + " МБ";
}

function initServiceSelect(selectEl) {
    API.getServices().then((services) => {
        selectEl.innerHTML = '<option value="">— Выберите службу —</option>' +
            services.map((s) => `<option value="${s.id}">${s.title}</option>`).join("");
    }).catch((e) => {
        selectEl.innerHTML = '<option value="">Ошибка загрузки служб</option>';
        console.error(e);
    });
}

function initUpload(dropZone, fileInput, fileSelectBtn, fileInfo, fileName, fileSize, progressContainer, progressBar, progressText, analyzeBtn) {
    let selectedFile = null;

    function showFileInfo(file) {
        fileName.textContent = file.name;
        fileSize.textContent = "Размер: " + formatSize(file.size);
        fileInfo.style.display = "block";
        fileInfo.classList.add("show");
        progressContainer.style.display = "none";
        progressContainer.classList.remove("show");
        progressText.innerHTML = "";
        analyzeBtn.disabled = false;
    }

    function chooseFile(file) {
        if (!file) return;
        const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
        const allowed = [".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"];
        if (!allowed.includes(ext)) {
            showError("Формат не поддерживается. Разрешены: PDF, DOCX, PNG, JPG, TIFF, BMP.");
            return;
        }
        if (file.size > 200 * 1024 * 1024) {
            showError("Файл больше 200 МБ. Максимальный размер: 200 МБ.");
            return;
        }
        selectedFile = file;
        showFileInfo(file);
        // Скрываем предыдущие результаты и ошибки
        document.getElementById("results-row").style.display = "none";
        document.getElementById("error-row").style.display = "none";
    }

    function showError(message) {
        const errorRow = document.getElementById("error-row");
        const errorMessage = document.getElementById("error-message");
        errorMessage.textContent = message;
        errorRow.style.display = "block";
        setTimeout(() => {
            errorRow.style.display = "none";
        }, 5000);
    }

    // Обработчики drag & drop
    dropZone.addEventListener("click", (e) => {
        if (e.target === fileSelectBtn || fileSelectBtn.contains(e.target)) {
            return; // Не вызываем клик на input, если кликнули на кнопку
        }
        fileInput.click();
    });
    
    dropZone.addEventListener("dragover", (e) => { 
        e.preventDefault(); 
        dropZone.classList.add("drag-over"); 
    });
    
    dropZone.addEventListener("dragleave", (e) => {
        // Проверяем, что мышь действительно покинула зону
        if (e.target === dropZone) {
            dropZone.classList.remove("drag-over");
        }
    });
    
    dropZone.addEventListener("drop", (e) => { 
        e.preventDefault(); 
        dropZone.classList.remove("drag-over"); 
        if (e.dataTransfer.files.length > 0) {
            chooseFile(e.dataTransfer.files[0]); 
        }
    });
    
    fileSelectBtn.addEventListener("click", (e) => { 
        e.stopPropagation(); 
        fileInput.click(); 
    });
    
    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            chooseFile(fileInput.files[0]);
        }
    });

    analyzeBtn.addEventListener("click", async () => {
        const serviceSelect = document.getElementById("service-select");
        const promptId = serviceSelect && serviceSelect.value;
        if (!promptId) { 
            showError("Выберите службу перед началом анализа.");
            return; 
        }
        if (!selectedFile) { 
            showError("Выберите файл договора.");
            return; 
        }

        // Скрываем предыдущие результаты и ошибки
        document.getElementById("results-row").style.display = "none";
        document.getElementById("error-row").style.display = "none";

        // Блокируем форму
        serviceSelect.disabled = true;
        dropZone.style.pointerEvents = "none";
        dropZone.style.opacity = "0.6";
        fileSelectBtn.disabled = true;

        // Показываем прогресс
        progressContainer.style.display = "block";
        progressContainer.classList.add("show");
        progressBar.style.width = "0%";
        updateProgressText("Отправка файла...", 0, "processing");
        analyzeBtn.disabled = true;
        analyzeBtn.classList.add("btn-processing");

        try {
            const { request_id } = await API.processDocument(selectedFile, promptId);
            updateProgressText("Обработка запущена", 3, "processing");

            const poll = async () => {
                const st = await API.getStatus(request_id);
                if (!st) return;
                
                const pct = Math.round(Number(st.progress) || 0);
                progressBar.style.width = pct + "%";
                
                // Формируем сообщение
                let msg = STATUS_MESSAGES[st.status] || st.message || "Обработка";
                if (st.status === 'ocr' && st.processed_pages != null && st.total_pages != null && st.total_pages > 0) {
                    msg = `Распознавание: страница ${st.processed_pages} из ${st.total_pages}`;
                }
                if (st.status === 'ocr_queued') {
                    // Число показываем только когда в очереди 2 и более (0 или 1 — просто «Запрос в очереди...»)
                    const n = st.queue_position;
                    msg = (st.message && st.message.trim()) || (n != null && n > 1 ? `Запрос в очереди... ${n}` : STATUS_MESSAGES['ocr_queued']);
                }
                
                updateProgressText(msg, pct, st.status);

                if (st.status === "complete") {
                    const result = await API.getResult(request_id);
                    if (result.success) {
                        // Очищаем текст от markdown форматирования
                        let protocolText = (result.protocol_text || "")
                            .replace(/\*\*([^*]+)\*\*/g, "$1")  // Убираем **жирный**
                            .replace(/^---+$/gm, "")  // Убираем ---
                            .replace(/^#+\s*/gm, "")  // Убираем # заголовки
                            .replace(/\n{3,}/g, "\n\n");  // Максимум 2 переноса подряд
                        
                        let letterText = (result.letter_text || "")
                            .replace(/\*\*([^*]+)\*\*/g, "$1")  // Убираем **жирный**
                            .replace(/^---+$/gm, "")  // Убираем ---
                            .replace(/^#+\s*/gm, "")  // Убираем # заголовки
                            .replace(/^.*СОПРОВОДИТЕЛЬНОЕ ПИСЬМО.*$/gim, "")  // Убираем заголовок письма
                            .replace(/^.*к Протоколу разногласий.*$/gim, "")  // Убираем подзаголовок
                            .replace(/\n{3,}/g, "\n\n");  // Максимум 2 переноса подряд
                        
                        document.getElementById("result-protocol").textContent = protocolText.trim();
                        document.getElementById("result-letter").textContent = letterText.trim();
                        document.getElementById("results-row").style.display = "block";
                        
                        const baseName = (selectedFile.name || "protocol").replace(/\.[^.]+$/, "");
                        document.getElementById("download-protocol-btn").onclick = () => {
                            API.exportWord(result.protocol_text, result.letter_text, baseName, "protocol");
                        };
                        document.getElementById("download-letter-btn").onclick = () => {
                            API.exportWord(result.protocol_text, result.letter_text, baseName, "letter");
                        };
                        
                        // Скрываем прогресс
                        progressContainer.classList.remove("show");
                        setTimeout(() => {
                            progressContainer.style.display = "none";
                        }, 300);
                    } else {
                        document.getElementById("error-message").textContent = result.error || "Ошибка обработки";
                        document.getElementById("error-row").style.display = "block";
                        progressContainer.classList.remove("show");
                        setTimeout(() => {
                            progressContainer.style.display = "none";
                        }, 300);
                    }
                    
                    // Разблокируем форму
                    const serviceSelect = document.getElementById("service-select");
                    serviceSelect.disabled = false;
                    dropZone.style.pointerEvents = "auto";
                    dropZone.style.opacity = "1";
                    fileSelectBtn.disabled = false;
                    analyzeBtn.disabled = false;
                    analyzeBtn.classList.remove("btn-processing");
                    return;
                }
                
                if (st.status === "error") {
                    document.getElementById("error-message").textContent = st.message || "Ошибка обработки";
                    document.getElementById("error-row").style.display = "block";
                    progressContainer.classList.remove("show");
                    setTimeout(() => {
                        progressContainer.style.display = "none";
                    }, 300);
                    
                    // Разблокируем форму
                    const serviceSelect = document.getElementById("service-select");
                    serviceSelect.disabled = false;
                    dropZone.style.pointerEvents = "auto";
                    dropZone.style.opacity = "1";
                    fileSelectBtn.disabled = false;
                    analyzeBtn.disabled = false;
                    analyzeBtn.classList.remove("btn-processing");
                    return;
                }
                
                setTimeout(poll, POLL_INTERVAL);
            };
            setTimeout(poll, POLL_INTERVAL);
        } catch (err) {
            progressContainer.classList.remove("show");
            setTimeout(() => {
                progressContainer.style.display = "none";
            }, 300);
            document.getElementById("error-message").textContent = err.message || "Ошибка запроса";
            document.getElementById("error-row").style.display = "block";
            
            // Разблокируем форму
            const serviceSelect = document.getElementById("service-select");
            serviceSelect.disabled = false;
            dropZone.style.pointerEvents = "auto";
            dropZone.style.opacity = "1";
            fileSelectBtn.disabled = false;
            analyzeBtn.disabled = false;
            analyzeBtn.classList.remove("btn-processing");
        }
    });

    function updateProgressText(message, percentage, phase) {
        const phaseInfo = STATUS_PHASES[phase] || STATUS_PHASES['processing'];
        progressText.innerHTML = `
            <span style="color: ${phaseInfo.color};">${message}</span>
            <span id="progress-percentage" style="color: ${phaseInfo.color}; font-weight: bold;">${percentage}%</span>
        `;
    }

    return { getSelectedFile: () => selectedFile };
}

document.addEventListener("DOMContentLoaded", () => {
    const serviceSelect = document.getElementById("service-select");
    initServiceSelect(serviceSelect);

    initUpload(
        document.getElementById("drop-zone"),
        document.getElementById("file-input"),
        document.getElementById("file-select-btn"),
        document.getElementById("file-info"),
        document.getElementById("file-name"),
        document.getElementById("file-size"),
        document.getElementById("progress-container"),
        document.getElementById("progress-bar"),
        document.getElementById("progress-text"),
        document.getElementById("analyze-btn"),
    );
});
