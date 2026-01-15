// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('fileInput');
const selectFileBtn = document.getElementById('selectFile');
const sampleFileBtn = document.getElementById('sampleFile');
const toolButtons = document.querySelectorAll('.tool-btn');
const searchBtn = document.querySelector('.search-btn');
const searchInput = document.querySelector('.seo-search');

// API Configuration
const API_BASE_URL = window.location.hostname === 'localhost' 
    ? 'http://localhost:8000' 
    : 'https://api.flipfile.online';

// Drag & Drop Events
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileUpload(files[0]);
    }
});

// File Selection
selectFileBtn.addEventListener('click', () => {
    fileInput.click();
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
    }
});

// Sample File
sampleFileBtn.addEventListener('click', async () => {
    try {
        // Download a sample PDF for testing
        const response = await fetch('https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf');
        const blob = await response.blob();
        const file = new File([blob], 'sample.pdf', { type: 'application/pdf' });
        handleFileUpload(file);
    } catch (error) {
        showNotification('Failed to load sample file', 'error');
    }
});

// Tool Buttons
toolButtons.forEach(button => {
    button.addEventListener('click', () => {
        const tool = button.dataset.tool;
        showToolModal(tool);
    });
});

// Search Functionality
searchBtn.addEventListener('click', performSearch);
searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        performSearch();
    }
});

// File Upload Handler
async function handleFileUpload(file) {
    // Validate file
    if (!file) {
        showNotification('No file selected', 'error');
        return;
    }

    if (file.size > 50 * 1024 * 1024) { // 50MB limit
        showNotification('File size exceeds 50MB limit', 'error');
        return;
    }

    // Show progress
    const progressContainer = document.createElement('div');
    progressContainer.className = 'progress-container';
    progressContainer.innerHTML = `
        <div class="progress-bar"></div>
        <p class="progress-text">Uploading...</p>
    `;
    dropZone.innerHTML = '';
    dropZone.appendChild(progressContainer);
    progressContainer.style.display = 'block';

    const progressBar = progressContainer.querySelector('.progress-bar');
    const progressText = progressContainer.querySelector('.progress-text');

    // Create FormData
    const formData = new FormData();
    formData.append('file', file);
    formData.append('tool', 'compress'); // Default tool

    try {
        // Simulate progress
        let progress = 0;
        const interval = setInterval(() => {
            progress += 5;
            progressBar.style.width = `${Math.min(progress, 90)}%`;
        }, 100);

        // Upload file
        const response = await fetch(`${API_BASE_URL}/upload`, {
            method: 'POST',
            body: formData
        });

        clearInterval(interval);
        progressBar.style.width = '100%';
        progressText.textContent = 'Processing...';

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        
        // Show success
        progressText.textContent = 'Complete! Downloading...';
        
        // Download the processed file
        setTimeout(() => {
            downloadFile(result.download_url, file.name);
            resetDropZone();
            showNotification('File processed successfully!', 'success');
        }, 1000);

    } catch (error) {
        console.error('Upload error:', error);
        resetDropZone();
        showNotification('Upload failed. Please try again.', 'error');
    }
}

// Helper Functions
function showToolModal(tool) {
    const modal = document.createElement('div');
    modal.className = 'tool-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <h3>${getToolName(tool)}</h3>
            <p>Please select a file to ${getToolName(tool).toLowerCase()}</p>
            <button onclick="fileInput.click()">Select File</button>
            <button onclick="this.closest('.tool-modal').remove()">Cancel</button>
        </div>
    `;
    document.body.appendChild(modal);
}

function getToolName(tool) {
    const toolNames = {
        'compress': 'Compress PDF',
        'convert-pdf-to-word': 'Convert PDF to Word',
        'merge': 'Merge PDFs',
        'split': 'Split PDF',
        'convert-word-to-pdf': 'Convert Word to PDF',
        'convert-excel-to-pdf': 'Convert Excel to PDF'
    };
    return toolNames[tool] || tool;
}

function downloadFile(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'download';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function resetDropZone() {
    dropZone.innerHTML = `
        <div class="drop-arrow">
            <span></span>
            <span></span>
            <span></span>
        </div>
        <div class="drop-content">
            <i class="upload-icon">📁</i>
            <p class="drop-hint">Drag & drop your files here</p>
            <p class="drop-sub">Supports PDF, JPG, PNG, DOCX, XLSX</p>
            <p class="file-limit">Max file size: 50MB</p>
        </div>
    `;
    dropZone.classList.remove('drag-over');
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

function performSearch() {
    const query = searchInput.value.trim();
    if (query) {
        window.location.href = `/tools?search=${encodeURIComponent(query)}`;
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('FlipFile initialized');
    
    // Check daily task limit
    const today = new Date().toDateString();
    const lastVisit = localStorage.getItem('lastVisit');
    
    if (lastVisit === today) {
        const tasksDone = parseInt(localStorage.getItem('tasksDone') || '0');
        if (tasksDone >= 3) {
            showNotification('Daily limit reached (3 tasks). Please try again tomorrow.', 'warning');
        }
    } else {
        localStorage.setItem('lastVisit', today);
        localStorage.setItem('tasksDone', '0');
    }
});
