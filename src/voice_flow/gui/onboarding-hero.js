(function () {
  "use strict";

  function addRibbons(svg) {
    if (!svg || svg.childNodes.length) {
      return;
    }
    try {
      var namespace = "http://www.w3.org/2000/svg";
      var first = document.createElementNS(namespace, "path");
      first.setAttribute("d", "M-80 220 C300 80 520 390 910 225 S1510 70 2010 280");
      first.setAttribute("fill", "none");
      first.setAttribute("stroke", "#fb923c");
      first.setAttribute("stroke-width", "34");
      first.setAttribute("stroke-opacity", "0.18");
      var second = document.createElementNS(namespace, "path");
      second.setAttribute("d", "M-60 820 C360 610 680 1010 1110 760 S1610 610 1990 840");
      second.setAttribute("fill", "none");
      second.setAttribute("stroke", "#818cf8");
      second.setAttribute("stroke-width", "46");
      second.setAttribute("stroke-opacity", "0.16");
      svg.appendChild(first);
      svg.appendChild(second);
    } catch (error) {
      // Decorative SVGs must never affect onboarding content.
    }
  }

  function initialize() {
    var ribbons = document.querySelectorAll(".s1-ribbons, #s1-ribbons, #s2-ribbons, #s3-ribbons");
    for (var index = 0; index < ribbons.length; index += 1) {
      addRibbons(ribbons[index]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize);
  } else {
    initialize();
  }
}());
