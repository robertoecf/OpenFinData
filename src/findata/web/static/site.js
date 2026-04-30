(() => {
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.documentElement;
  const pointer = {
    targetX: window.innerWidth * 0.52,
    targetY: window.innerHeight * 0.42,
    x: window.innerWidth * 0.52,
    y: window.innerHeight * 0.42,
    active: false,
  };

  const setPointerVars = () => {
    const width = Math.max(window.innerWidth, 1);
    const height = Math.max(window.innerHeight, 1);
    const ratioX = pointer.x / width;
    const ratioY = pointer.y / height;

    root.style.setProperty("--cursor-x", `${pointer.x.toFixed(2)}px`);
    root.style.setProperty("--cursor-y", `${pointer.y.toFixed(2)}px`);
    root.style.setProperty("--mouse-ratio-x", ratioX.toFixed(4));
    root.style.setProperty("--mouse-ratio-y", ratioY.toFixed(4));
    root.style.setProperty("--grid-x", `${(-20 * ratioX).toFixed(2)}px`);
    root.style.setProperty("--grid-y", `${(-18 * ratioY).toFixed(2)}px`);
    root.style.setProperty("--horizon-x", `${((ratioX - 0.5) * 30).toFixed(2)}px`);
    root.style.setProperty("--parallax-x", `${((ratioX - 0.5) * 28).toFixed(2)}px`);
    root.style.setProperty("--parallax-y", `${((ratioY - 0.5) * 22).toFixed(2)}px`);
    root.style.setProperty("--stage-x", `${(ratioX * 100).toFixed(2)}%`);
    root.style.setProperty("--stage-y", `${(ratioY * 100).toFixed(2)}%`);
  };

  const trackPointer = () => {
    if (prefersReduced) return;

    window.addEventListener(
      "pointermove",
      (event) => {
        pointer.targetX = event.clientX;
        pointer.targetY = event.clientY;
        if (!pointer.active) {
          pointer.active = true;
        }
      },
      { passive: true },
    );

    window.addEventListener(
      "pointerleave",
      () => {
        pointer.active = false;
      },
      { passive: true },
    );
  };

  const animatePointerVars = () => {
    pointer.x += (pointer.targetX - pointer.x) * 0.1;
    pointer.y += (pointer.targetY - pointer.y) * 0.1;
    setPointerVars();
    window.requestAnimationFrame(animatePointerVars);
  };

  const reveal = () => {
    const nodes = document.querySelectorAll(".reveal");
    if (prefersReduced || !("IntersectionObserver" in window)) {
      nodes.forEach((node) => node.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.12 },
    );
    nodes.forEach((node) => observer.observe(node));
  };

  const bindCopy = () => {
    document.querySelectorAll("[data-copy]").forEach((node) => {
      const button = node.matches("button") ? node : node.querySelector("button");
      if (!button) return;
      const original = button.textContent;
      button.addEventListener("click", async () => {
        const value = node.getAttribute("data-copy") || "pip install findata-br";
        await navigator.clipboard?.writeText(value);
        button.textContent = document.documentElement.lang === "pt-BR" ? "copiado" : "Copied";
        window.setTimeout(() => {
          button.textContent = original;
        }, 1400);
      });
    });
  };

  const bindEndpointFilters = () => {
    const input = document.querySelector("[data-endpoint-search]");
    const select = document.querySelector("[data-endpoint-select]");
    const cards = Array.from(document.querySelectorAll(".endpoint-card"));
    if (!input || !select || !cards.length) return;

    const apply = () => {
      const query = input.value.trim().toLowerCase();
      const category = select.value.trim().toLowerCase();
      cards.forEach((card) => {
        const haystack = `${card.textContent} ${card.getAttribute("data-tags") || ""}`.toLowerCase();
        const matchesQuery = !query || haystack.includes(query);
        const matchesCategory = !category || haystack.includes(category);
        card.classList.toggle("is-hidden", !matchesQuery || !matchesCategory);
      });
    };

    input.addEventListener("input", apply);
    select.addEventListener("change", apply);
  };

  const bindTilt = () => {
    if (prefersReduced) return;
    document.querySelectorAll(".tilt").forEach((node) => {
      let raf = 0;
      let nextX = 50;
      let nextY = 50;
      let currentTiltX = 0;
      let currentTiltY = 0;
      let nextTiltX = 0;
      let nextTiltY = 0;

      const render = () => {
        currentTiltX += (nextTiltX - currentTiltX) * 0.16;
        currentTiltY += (nextTiltY - currentTiltY) * 0.16;
        node.style.setProperty("--card-x", `${nextX.toFixed(2)}%`);
        node.style.setProperty("--card-y", `${nextY.toFixed(2)}%`);
        node.style.setProperty("--tilt-x", `${currentTiltX.toFixed(3)}deg`);
        node.style.setProperty("--tilt-y", `${currentTiltY.toFixed(3)}deg`);
        raf = window.requestAnimationFrame(render);
      };

      node.addEventListener("pointerenter", () => {
        node.style.setProperty("--lift", "-4px");
        if (!raf) raf = window.requestAnimationFrame(render);
      });

      node.addEventListener("pointermove", (event) => {
        const rect = node.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width;
        const y = (event.clientY - rect.top) / rect.height;
        nextX = x * 100;
        nextY = y * 100;
        nextTiltX = (0.5 - y) * 5;
        nextTiltY = (x - 0.5) * 6;
      });

      node.addEventListener("pointerleave", () => {
        node.style.setProperty("--lift", "0px");
        nextTiltX = 0;
        nextTiltY = 0;
        nextX = 50;
        nextY = 0;
        window.setTimeout(() => {
          if (Math.abs(currentTiltX) < 0.02 && Math.abs(currentTiltY) < 0.02) {
            window.cancelAnimationFrame(raf);
            raf = 0;
            node.style.removeProperty("--tilt-x");
            node.style.removeProperty("--tilt-y");
          }
        }, 520);
      });
    });
  };

  const hydrateStats = async () => {
    try {
      const response = await fetch("stats", { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const stats = await response.json();
      const set = (selector, value) => {
        const node = document.querySelector(selector);
        if (node) node.textContent = value;
      };
      set("[data-live='version']", `v${stats.version}`);
      set("[data-live='cache']", `${stats.cache.size}/${stats.cache.max_size}`);
      set("[data-live='mcp']", stats.mcp_enabled ? "ativo" : "indisponível");
      set("[data-live='limits']", stats.rate_limits.enabled ? "ativo" : "desligado");
      set("[data-stat='source-count']", String(stats.sources.length));
    } catch {
      // The landing page remains useful as a static shell when stats are unavailable.
    }
  };

  const drawField = () => {
    const canvas = document.querySelector(".field");
    if (!canvas || prefersReduced) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const colors = ["0, 168, 89", "255, 223, 0", "0, 80, 255", "255, 138, 0"];
    const points = Array.from({ length: 42 }, (_, index) => ({
      x: Math.random(),
      y: Math.random(),
      speed: 0.00024 + Math.random() * 0.00048,
      phase: Math.random() * Math.PI * 2,
      color: colors[index % colors.length],
    }));

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(window.innerWidth * ratio);
      canvas.height = Math.floor(window.innerHeight * ratio);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const tick = (time) => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      ctx.clearRect(0, 0, width, height);

      points.forEach((point, index) => {
        const driftX = ((point.x + time * point.speed) % 1) * width;
        const driftY = (point.y + Math.sin(time * 0.0008 + point.phase) * 0.014) * height;
        const influence = pointer.active ? 0.055 : 0.018;
        const x = driftX + (pointer.x - width / 2) * influence;
        const y = driftY + (pointer.y - height / 2) * influence;

        ctx.beginPath();
        ctx.arc(x, y, point.color === "255, 223, 0" ? 1.65 : 1.35, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${point.color}, ${point.color === "255, 223, 0" ? 0.28 : 0.24})`;
        ctx.fill();

        const next = points[(index + 8) % points.length];
        const x2 = ((next.x + time * next.speed) % 1) * width + (pointer.x - width / 2) * influence;
        const y2 = (next.y + Math.cos(time * 0.0008 + next.phase) * 0.014) * height + (pointer.y - height / 2) * influence;
        const distance = Math.hypot(x - x2, y - y2);
        if (distance < 330) {
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x2, y2);
          ctx.strokeStyle = `rgba(${point.color}, ${0.13 * (1 - distance / 330)})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });

      if (pointer.active) {
        const gradient = ctx.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 210);
        gradient.addColorStop(0, "rgba(255, 223, 0, 0.13)");
        gradient.addColorStop(0.42, "rgba(0, 168, 89, 0.06)");
        gradient.addColorStop(1, "rgba(0, 80, 255, 0)");
        ctx.fillStyle = gradient;
        ctx.fillRect(pointer.x - 210, pointer.y - 210, 420, 420);
      }

      window.requestAnimationFrame(tick);
    };

    resize();
    window.addEventListener("resize", resize, { passive: true });
    window.requestAnimationFrame(tick);
  };

  trackPointer();
  animatePointerVars();
  reveal();
  bindCopy();
  bindEndpointFilters();
  bindTilt();
  hydrateStats();
  drawField();
})();
