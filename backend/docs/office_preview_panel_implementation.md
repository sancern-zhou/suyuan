# Office Document Real-time Preview Panel - Implementation Summary

## Overview
Successfully implemented Office document real-time preview panel functionality for the Air Pollution Source Traceability System. This feature allows users to preview Word/PPT documents in real-time as the Agent edits them.

## Architecture

### Backend Components

#### 1. PDF Converter Service (`app/services/pdf_converter.py`)
- **Purpose**: Convert Office documents (DOCX/PPTX) to PDF for frontend preview
- **Key Features**:
  - Uses LibreOffice (`soffice`) for conversion
  - Caches converted PDFs in temp directory
  - Returns PDF metadata (ID, URL, page count, size)
  - Graceful error handling (PDF conversion failure doesn't break main functionality)

#### 2. Office API Routes (`app/api/office_routes.py`)
- **Endpoints**:
  - `GET /api/office/pdf/{pdf_id}` - Retrieve PDF file
  - `GET /api/office/pdf/{pdf_id}/info` - Get PDF metadata
  - `POST /api/office/apply-edit` - Apply user edits to documents
  - `DELETE /api/office/pdf/{pdf_id}` - Delete cached PDF

#### 3. Office Tools Integration
Modified the following tools to include PDF conversion:
- `accept_changes_tool.py` - Word revision acceptance
- `find_replace_tool.py` - Word find/replace
- `word_edit_tool.py` - Word structured editing
- `pack_tool.py` - Office file packing

Each tool now:
1. Performs its original operation
2. Attempts PDF conversion (non-blocking)
3. Includes `pdf_preview` in response data if successful
4. Logs warnings if conversion fails (doesn't affect main function)

### Frontend Components

#### 1. Office Document Panel (`frontend/src/components/OfficeDocumentPanel.vue`)
- **Features**:
  - Real-time PDF preview with iframe
  - Smooth transition animations (loading fade-in/out)
  - Edit mode with textarea for content modification
  - Edit history (last 5 actions)
  - Expand/collapse functionality
  - Empty state when no documents available

- **States**:
  - Preview mode: Shows PDF in iframe
  - Edit mode: Shows textarea for content editing
  - Loading state: Spinner during PDF refresh
  - Error state: Message if PDF fails to load

#### 2. Integration with ReactAnalysisView
- Added `OfficeDocumentPanel` alongside `VisualizationPanel`
- Auto-detects Office tool operations in message history
- Shows panel when Office documents are being edited
- Handles user edit submissions

## Data Flow

```
User Request → ReAct Agent → Office Tool Execution → PDF Conversion
                                                              ↓
SSE Event → Frontend Message History → OfficeDocumentPanel → PDF Preview
                                                              ↓
                                                        User Views Document
```

## Key Technical Decisions

1. **PDF-based Preview**: Using PDF conversion instead of native Office rendering
   - Pros: Works across all platforms, no browser plugins needed
   - Cons: Requires LibreOffice installation

2. **Non-blocking Conversion**: PDF conversion failures don't break Office tools
   - Tools continue to work even if PDF conversion fails
   - Only affects the preview feature

3. **Lazy Loading**: PDF converter is loaded on-demand to avoid circular imports
   - Uses function-based import pattern

4. **Animation Strategy**: Simple loading state + CSS transition
   - 300ms delay for smooth visual feedback
   - Fade-in effect when new PDF loads

## Dependencies

### Backend
- `pypdf>=5.0.0` - Added to requirements.txt
- Requires LibreOffice (`soffice` command)

### Frontend
- No new dependencies (uses browser native iframe)

## Files Modified/Created

### Backend (8 files)
1. `backend/app/services/pdf_converter.py` - NEW
2. `backend/app/api/office_routes.py` - NEW
3. `backend/app/main.py` - MODIFIED (added office routes)
4. `backend/app/tools/office/accept_changes_tool.py` - MODIFIED
5. `backend/app/tools/office/find_replace_tool.py` - MODIFIED
6. `backend/app/tools/office/word_edit_tool.py` - MODIFIED
7. `backend/app/tools/office/pack_tool.py` - MODIFIED
8. `backend/requirements.txt` - MODIFIED (added pypdf)

### Frontend (2 files)
1. `frontend/src/components/OfficeDocumentPanel.vue` - NEW
2. `frontend/src/views/ReactAnalysisView.vue` - MODIFIED

## Testing

### Manual Testing Steps
1. Start backend: `cd backend && python -m uvicorn app.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Upload a Word document with revisions
4. Request: "接受这个文档的所有修订" (Accept all revisions)
5. Verify:
   - Office panel appears on the right
   - PDF preview loads with animation
   - Document title and edit history shown
   - Edit mode allows content modification

### Automated Testing
- Created `backend/tests/test_pdf_converter.py` for unit testing

## Error Handling

1. **LibreOffice Not Available**: Tools continue to work, preview unavailable
2. **PDF Conversion Timeout**: Logged as warning, doesn't block tool execution
3. **Large Files**: No specific limit (LibreOffice handles it)
4. **Network Issues**: PDF loading fails gracefully with error message

## Future Enhancements

1. **Direct Integration**: Apply edits through Agent instead of manual API call
2. **Multiple Documents**: Support simultaneous preview of multiple documents
3. **Version History**: Track document versions with diff view
4. **Download PDF**: Allow users to download PDF preview
5. **Thumbnail Generation**: Show document thumbnails in list view

## Notes

- PDF files are cached in `/tmp/office_pdf_cache` (or OS equivalent)
- PDFs persist until explicitly deleted or system cleanup
- Each PDF has a unique UUID for isolation
- Panel automatically shows/hides based on message history
