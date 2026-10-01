/**
 * Backward compatibility wrapper for Kodewaves Widget.
 * This file delegates all functionality to kodewaves-widget.js while preserving
 * window.DograhWidget and data-dograh-context attributes.
 */
(function() {
  'use strict';

  var currentScript = document.currentScript;
  var targetUrl = '/embed/kodewaves-widget.js';

  if (currentScript && currentScript.src) {
    targetUrl = currentScript.src.replace(/dograh-widget\.js/, 'kodewaves-widget.js');
  }

  // Load the canonical Kodewaves widget script
  var script = document.createElement('script');
  script.src = targetUrl;
  script.async = true;

  if (currentScript) {
    for (var i = 0; i < currentScript.attributes.length; i++) {
      var attr = currentScript.attributes[i];
      if (attr.name !== 'src') {
        script.setAttribute(attr.name, attr.value);
      }
    }
    currentScript.parentNode.insertBefore(script, currentScript.nextSibling);
  } else {
    document.head.appendChild(script);
  }
})();
