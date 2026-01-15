import os
import uuid
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import aiofiles
from pydantic import BaseModel

# Import PDF processing libraries
try:
    from pdf2docx import Converter
    import pikepdf
    import PyPDF2
    import img2pdf
    from docx import Document
    import pandas as pd
    HAS_PDF_LIBS = True
except ImportError:
    HAS_PDF_LIBS = False
    print("Warning: Some PDF libraries not installed. Install with: pip install pdf2docx pikepdf PyPDF2 img2pdf python-docx pandas")

app = FastAPI(title="FlipFile API", version="1.0.0")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://flipfile.online", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.docx', '.xlsx'}
CLEANUP_INTERVAL = 3600  # 1 hour

class FileUpload(BaseModel):
    tool: str = "compress"
    quality: Optional[str] = "high"

# Rate limiting storage (in production, use Redis)
task_counts = {}

async def cleanup_old_files():
    """Clean up files older than 1 hour"""
    now = datetime.now()
    for file_path in UPLOAD_DIR.glob("*"):
        if file_path.is_file():
            file_age = now - datetime.fromtimestamp(file_path.stat().st_mtime)
            if file_age > timedelta(hours=1):
                try:
                    file_path.unlink()
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(periodic_cleanup())

async def periodic_cleanup():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        await cleanup_old_files()

@app.get("/")
async def root():
    return {"message": "FlipFile API", "status": "online", "version": "1.0.0"}

@app.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tool: str = "compress",
    quality: str = "high"
):
    """
    Handle file uploads with various processing tools
    """
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {file_ext} not allowed")
    
    # Read file size
    content = await file.read()
    file_size = len(content)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Max {MAX_FILE_SIZE/1024/1024}MB")
    
    # Reset file pointer
    await file.seek(0)
    
    # Generate unique filename
    file_id = str(uuid.uuid4())
    original_path = UPLOAD_DIR / f"{file_id}_original{file_ext}"
    processed_path = UPLOAD_DIR / f"{file_id}_processed.pdf"
    
    # Save original file
    async with aiofiles.open(original_path, 'wb') as f:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            await f.write(chunk)
    
    try:
        # Process based on tool
        if tool == "compress":
            await compress_pdf(original_path, processed_path, quality)
        elif tool == "convert-pdf-to-word":
            await pdf_to_word(original_path, processed_path)
        elif tool == "merge":
            # For merge, we'd need multiple files
            pass
        elif tool == "split":
            await split_pdf(original_path, processed_path)
        elif file_ext == '.docx':
            await word_to_pdf(original_path, processed_path)
        elif file_ext in ['.jpg', '.jpeg', '.png']:
            await image_to_pdf(original_path, processed_path)
        elif file_ext == '.xlsx':
            await excel_to_pdf(original_path, processed_path)
        else:
            # Default: just copy
            processed_path = original_path
        
        # Schedule cleanup
        background_tasks.add_task(delete_file, original_path)
        background_tasks.add_task(delete_file, processed_path)
        
        # Return download URL
        download_url = f"/download/{processed_path.name}"
        
        return JSONResponse({
            "status": "success",
            "message": "File processed successfully",
            "download_url": download_url,
            "file_id": file_id,
            "original_name": file.filename,
            "processed_name": processed_path.name,
            "file_size": file_size
        })
        
    except Exception as e:
        # Clean up on error
        if original_path.exists():
            original_path.unlink()
        if processed_path.exists():
            processed_path.unlink()
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download processed files"""
    file_path = UPLOAD_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check if file is too old
    file_age = datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)
    if file_age > timedelta(hours=1):
        file_path.unlink()
        raise HTTPException(status_code=410, detail="File expired")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )

@app.get("/tools")
async def list_tools():
    """List available tools"""
    tools = [
        {"id": "compress", "name": "Compress PDF", "description": "Reduce PDF file size"},
        {"id": "convert-pdf-to-word", "name": "PDF to Word", "description": "Convert PDF to editable DOCX"},
        {"id": "merge", "name": "Merge PDF", "description": "Combine multiple PDFs"},
        {"id": "split", "name": "Split PDF", "description": "Split PDF into multiple files"},
        {"id": "convert-word-to-pdf", "name": "Word to PDF", "description": "Convert DOCX to PDF"},
        {"id": "convert-excel-to-pdf", "name": "Excel to PDF", "description": "Convert XLSX to PDF"},
        {"id": "image-to-pdf", "name": "Image to PDF", "description": "Convert images to PDF"},
        {"id": "pdf-to-image", "name": "PDF to Image", "description": "Convert PDF pages to images"},
    ]
    return {"tools": tools}

async def compress_pdf(input_path: Path, output_path: Path, quality: str = "high"):
    """Compress PDF file"""
    if not HAS_PDF_LIBS:
        raise Exception("PDF libraries not installed")
    
    with pikepdf.open(input_path) as pdf:
        # Apply compression based on quality
        if quality == "low":
            save_options = pikepdf.SaveOptions(compress_streams=True, stream_compression_level=9)
        elif quality == "medium":
            save_options = pikepdf.SaveOptions(compress_streams=True, stream_compression_level=6)
        else:  # high
            save_options = pikepdf.SaveOptions(compress_streams=True)
        
        pdf.save(output_path, options=save_options)

async def pdf_to_word(input_path: Path, output_path: Path):
    """Convert PDF to Word document"""
    if not HAS_PDF_LIBS:
        raise Exception("PDF libraries not installed")
    
    # Convert PDF to DOCX
    cv = Converter(str(input_path))
    cv.convert(str(output_path).replace('.pdf', '.docx'), start=0, end=None)
    cv.close()

async def split_pdf(input_path: Path, output_path: Path):
    """Split PDF into individual pages"""
    if not HAS_PDF_LIBS:
        raise Exception("PDF libraries not installed")
    
    with open(input_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        
        for i, page in enumerate(pdf_reader.pages):
            pdf_writer = PyPDF2.PdfWriter()
            pdf_writer.add_page(page)
            
            page_path = output_path.parent / f"{output_path.stem}_page_{i+1}.pdf"
            with open(page_path, 'wb') as output_file:
                pdf_writer.write(output_file)

async def image_to_pdf(input_path: Path, output_path: Path):
    """Convert image to PDF"""
    if not HAS_PDF_LIBS:
        raise Exception("Image to PDF libraries not installed")
    
    with open(output_path, "wb") as f:
        f.write(img2pdf.convert(input_path))

async def word_to_pdf(input_path: Path, output_path: Path):
    """Convert Word document to PDF (simplified)"""
    # Note: This is a simplified version. For production, consider using LibreOffice or cloud services
    if not HAS_PDF_LIBS:
        raise Exception("Word to PDF libraries not installed")
    
    # This is a placeholder - actual Word to PDF conversion requires additional libraries
    # like python-docx2pdf or using an external service
    raise NotImplementedError("Word to PDF conversion requires additional setup")

async def excel_to_pdf(input_path: Path, output_path: Path):
    """Convert Excel to PDF (simplified)"""
    if not HAS_PDF_LIBS:
        raise Exception("Excel to PDF libraries not installed")
    
    # Placeholder - actual Excel to PDF requires additional setup
    raise NotImplementedError("Excel to PDF conversion requires additional setup")

async def delete_file(file_path: Path):
    """Delete file after delay"""
    await asyncio.sleep(CLEANUP_INTERVAL)
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        print(f"Error deleting {file_path}: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
