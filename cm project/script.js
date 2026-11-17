const contentArea = document.getElementById("contentArea");
const pageTitle = document.getElementById("pageTitle");
const pageDesc = document.getElementById("pageDesc");
const backBtn = document.getElementById("backBtn");

const viewerOverlay = document.getElementById("viewerOverlay");
const viewerBody = document.getElementById("viewerBody");
const viewerTitle = document.getElementById("viewerTitle");
const viewerSubtitle = document.getElementById("viewerSubtitle");
const closeViewerBtn = document.getElementById("closeViewerBtn");

let courseData = null;
let currentCourse = null;
let currentModuleIndex = null;

async function init() {
  try {
    const res = await fetch("course.json", { cache: "no-store" });
    if (!res.ok) throw new Error("Unable to load course.json");

    courseData = await res.json();

    if (
      !courseData ||
      !Array.isArray(courseData.courses) ||
      courseData.courses.length === 0
    ) {
      throw new Error("Invalid JSON structure");
    }

    currentCourse = courseData.courses[0];

    if (!currentCourse || !Array.isArray(currentCourse.modules)) {
      throw new Error("Invalid course/modules structure");
    }

    const urlParams = new URLSearchParams(window.location.search);
    const moduleIndex = urlParams.get("module");

    if (
      moduleIndex !== null &&
      moduleIndex !== "" &&
      !Number.isNaN(Number(moduleIndex)) &&
      currentCourse.modules[Number(moduleIndex)]
    ) {
      renderChapters(Number(moduleIndex));
    } else {
      renderModules();
    }
  } catch (error) {
    contentArea.innerHTML = `
      <div class="empty-state">
        Failed to load course data.
        <br>
        <small>${escapeHtml(error.message)}</small>
      </div>
    `;
  }
}

function renderModules() {
  backBtn.classList.add("hidden");
  currentModuleIndex = null;

  const courseName = currentCourse?.course_name || "All Modules";

  pageTitle.textContent = courseName;
  pageDesc.textContent = "Select a module to view all chapters.";

  if (!currentCourse || !Array.isArray(currentCourse.modules) || currentCourse.modules.length === 0) {
    contentArea.innerHTML = `<div class="empty-state">No modules found.</div>`;
    return;
  }

  contentArea.innerHTML = `
    <div class="module-grid">
      ${currentCourse.modules.map((module, index) => {
        const moduleName = module.module_name || `Module ${module.module_order || index + 1}`;
        const chapterCount = Array.isArray(module.chapters) ? module.chapters.length : 0;

        return `
          <div class="module-card" data-module-index="${index}">
            <span class="module-badge">${escapeHtml(module.module_id || `MOD_${index + 1}`)}</span>
            <h3 class="module-title">${escapeHtml(moduleName)}</h3>
            <div class="module-meta">${chapterCount} chapters available</div>
            <div class="module-open">Open Module →</div>
          </div>
        `;
      }).join("")}
    </div>
  `;

  document.querySelectorAll(".module-card").forEach(card => {
    card.addEventListener("click", () => {
      const index = Number(card.getAttribute("data-module-index"));
      openModule(index);
    });
  });
}

function openModule(index) {
  const url = new URL(window.location.href);
  url.searchParams.set("module", index);
  history.pushState({}, "", url);
  renderChapters(index);
}

function renderChapters(index) {
  if (
    !currentCourse ||
    !Array.isArray(currentCourse.modules) ||
    !currentCourse.modules[index]
  ) {
    renderModules();
    return;
  }

  currentModuleIndex = index;
  backBtn.classList.remove("hidden");

  const module = currentCourse.modules[index];
  const moduleName = module.module_name || `Module ${module.module_order || index + 1}`;
  const chapters = Array.isArray(module.chapters) ? module.chapters : [];

  pageTitle.textContent = moduleName;
  pageDesc.textContent = "Watch video or read PDF notes.";

  if (chapters.length === 0) {
    contentArea.innerHTML = `<div class="empty-state">No chapters found for this module.</div>`;
    return;
  }

  contentArea.innerHTML = `
    <div class="chapters-wrap">
      <div class="row-head">
        <div>Chapter Name</div>
        <div>Show Video</div>
        <div>Show PDF Note</div>
      </div>

      ${chapters.map((chapter, i) => {
        const chapterTitle = chapter.chapter_title || `Chapter ${chapter.chapter_order || i + 1}`;
        const chapterDesc = chapter.status ? `Status: ${chapter.status}` : `Lesson ${chapter.chapter_order || i + 1}`;

        return `
          <div class="chapter-row">
            <div class="chapter-title-box">
              <h3>${escapeHtml(chapterTitle)}</h3>
              <p>${escapeHtml(chapterDesc)}</p>
            </div>

            <div>
              ${chapter.video_url
                ? `<button class="btn btn-primary action-btn" data-type="video" data-module="${index}" data-chapter="${i}">Show Video</button>`
                : `<div class="no-file">No Video</div>`
              }
            </div>

            <div>
              ${chapter.pdf_url
                ? `<button class="btn btn-success action-btn" data-type="pdf" data-module="${index}" data-chapter="${i}">Show PDF</button>`
                : `<div class="no-file">No PDF</div>`
              }
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;

  document.querySelectorAll(".action-btn").forEach(button => {
    button.addEventListener("click", () => {
      const type = button.getAttribute("data-type");
      const moduleIndex = Number(button.getAttribute("data-module"));
      const chapterIndex = Number(button.getAttribute("data-chapter"));
      openViewer(type, moduleIndex, chapterIndex);
    });
  });
}

function openViewer(type, moduleIndex, chapterIndex) {
  if (
    !currentCourse ||
    !currentCourse.modules ||
    !currentCourse.modules[moduleIndex] ||
    !currentCourse.modules[moduleIndex].chapters ||
    !currentCourse.modules[moduleIndex].chapters[chapterIndex]
  ) {
    return;
  }

  const module = currentCourse.modules[moduleIndex];
  const chapter = module.chapters[chapterIndex];

  const moduleTitle = module.module_name || `Module ${module.module_order || moduleIndex + 1}`;
  const chapterTitle = chapter.chapter_title || `Chapter ${chapter.chapter_order || chapterIndex + 1}`;

  viewerBody.innerHTML = "";
  viewerOverlay.classList.remove("hidden");
  document.body.classList.add("no-scroll");

  viewerTitle.textContent = `${moduleTitle} - ${chapterTitle}`;
  viewerSubtitle.textContent = type === "video" ? "Watch mode" : "Read mode";

  if (type === "video") {
    openVideoViewer(chapter.video_url);
  } else {
    openPdfViewer(chapter.pdf_url);
  }
}

function openVideoViewer(videoSrc) {
  const wrap = document.createElement("div");
  wrap.style.height = "100%";
  wrap.style.display = "flex";
  wrap.style.flexDirection = "column";

  const note = document.createElement("div");
  note.className = "viewer-note";
  note.textContent = "Video fullscreen is allowed.";

  const video = document.createElement("video");
  video.className = "viewer-video";
  video.src = videoSrc;
  video.controls = true;
  video.controlsList = "nodownload noplaybackrate noremoteplayback";
  video.disablePictureInPicture = false;
  video.setAttribute("playsinline", "true");
  video.setAttribute("preload", "metadata");
  video.setAttribute("oncontextmenu", "return false;");

  wrap.appendChild(note);
  wrap.appendChild(video);
  viewerBody.appendChild(wrap);
}

function openPdfViewer(pdfSrc) {
  const wrap = document.createElement("div");
  wrap.style.height = "100%";
  wrap.style.display = "flex";
  wrap.style.flexDirection = "column";

  const note = document.createElement("div");
  note.className = "viewer-note";
  note.textContent = "PDF read mode is opened below.";

  const iframe = document.createElement("iframe");
  iframe.className = "viewer-frame";
  iframe.src = `${pdfSrc}#toolbar=0&navpanes=0&scrollbar=1&view=FitH`;
  iframe.setAttribute("referrerpolicy", "no-referrer");
  iframe.setAttribute("oncontextmenu", "return false;");

  const fallback = document.createElement("div");
  fallback.className = "pdf-fallback hidden";
  fallback.innerHTML = `
    <div class="pdf-fallback-box">
      <h4>PDF viewer blocked by browser</h4>
      <p>Open this project on localhost/server and make sure PDF path is correct.</p>
      <p class="pdf-path">${escapeHtml(pdfSrc)}</p>
    </div>
  `;

  let loaded = false;

  iframe.addEventListener("load", () => {
    loaded = true;
  });

  setTimeout(() => {
    if (!loaded) {
      fallback.classList.remove("hidden");
    }
  }, 2500);

  wrap.appendChild(note);
  wrap.appendChild(iframe);
  wrap.appendChild(fallback);
  viewerBody.appendChild(wrap);
}

function closeViewer() {
  viewerOverlay.classList.add("hidden");
  viewerBody.innerHTML = "";
  document.body.classList.remove("no-scroll");
}

function goBack() {
  closeViewer();

  const url = new URL(window.location.href);
  url.searchParams.delete("module");
  history.pushState({}, "", url);

  renderModules();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

backBtn.addEventListener("click", goBack);
closeViewerBtn.addEventListener("click", closeViewer);

viewerOverlay.addEventListener("click", (e) => {
  if (e.target === viewerOverlay) {
    closeViewer();
  }
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeViewer();
  }
});

window.addEventListener("popstate", () => {
  const urlParams = new URLSearchParams(window.location.search);
  const moduleIndex = urlParams.get("module");

  closeViewer();

  if (
    moduleIndex !== null &&
    moduleIndex !== "" &&
    !Number.isNaN(Number(moduleIndex)) &&
    currentCourse &&
    currentCourse.modules &&
    currentCourse.modules[Number(moduleIndex)]
  ) {
    renderChapters(Number(moduleIndex));
  } else {
    renderModules();
  }
});

document.addEventListener("contextmenu", (e) => {
  if (!viewerOverlay.classList.contains("hidden")) {
    e.preventDefault();
  }
});

init();