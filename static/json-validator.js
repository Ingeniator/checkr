import { initPyodide } from './pyodide-loader.js';

class JsonValidator extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 1rem;
          background: #f9f9f9;
          border: 1px solid #ccc;
          border-radius: 8px;
          max-width: 900px;
        }
        textarea.input-data {
          width: 98%;
          height: 150px;
          margin-bottom: 10px;
          padding: 8px;
          font-family: monospace;
        }
        pre {
          background: #eee;
          padding: 10px;
          white-space: pre-wrap;
          border-radius: 4px;
        }
        button {
          padding: 8px 16px;
          font-size: 1rem;
          cursor: pointer;
          margin-top: 10px;
          margin-right: 10px;
        }
        textarea.validator-options {
          width: 100%;
          min-height: 60px;
          max-height: 600px;
          resize: none;
          overflow: hidden;
          font-family: monospace;
          box-sizing: border-box;
          padding: 8px;
        }
        .input-tabs {
          display: flex;
          gap: 0;
          margin-bottom: 0;
        }
        .input-tabs button {
          padding: 6px 16px;
          font-size: 0.9rem;
          cursor: pointer;
          border: 1px solid #ccc;
          background: #e9e9e9;
          color: #555;
          margin: 0;
          border-bottom: none;
          border-radius: 6px 6px 0 0;
        }
        .input-tabs button.active {
          background: #fff;
          color: #111;
          font-weight: 600;
          border-bottom: 1px solid #fff;
          position: relative;
          z-index: 1;
        }
        .url-input-row {
          display: flex;
          gap: 8px;
          margin-bottom: 10px;
        }
        .url-input-row input {
          flex: 1;
          padding: 8px;
          font-family: monospace;
          font-size: 0.9rem;
          border: 1px solid #ccc;
          border-radius: 4px;
        }
        .url-input-row button {
          margin: 0;
          white-space: nowrap;
        }
      </style>
      <div class="input-tabs">
        <button id="tab-paste" class="active">Paste JSON</button>
        <button id="tab-url">Load from URL</button>
      </div>
      <textarea class="input-data" id="input" placeholder="Paste JSON here..."></textarea>
      <div class="url-input-row" id="url-row" style="display: none;">
        <input type="text" id="url-input" placeholder="https://example.com/dataset.json">
        <button id="fetch-url">Fetch</button>
      </div>
      <h2>Available Validators:</h2>
      <div id="validator-list"></div>
      <button id="validate" style="display: none;">Validate</button>
      <button id="submit" style="display: none;">Submit</button>
      <pre id="progress">Validation progress will appear here</pre>
      <pre id="output">Validation output will appear here</pre>
    `;
  }

  renderHierarchicalValidators(container, validators) {
    const grouped = {};

    validators.forEach(v => {
      const group = v.folder;
      if (!grouped[group]) grouped[group] = [];
      grouped[group].push(v);
    });

    container.innerHTML = Object.entries(grouped)
      .sort(([a], [b]) => {
        const numA = parseInt(a.match(/\d+/)?.[0] ?? "0", 10);
        const numB = parseInt(b.match(/\d+/)?.[0] ?? "0", 10);
        return numA - numB;
      })
      .map(([folder, items]) => {
      return `
        <h3 class="folder"># ${folder.replaceAll("_", " ")}</h3>
        ${items.map(v => {
          // Determine the label
          let labelText = v.description
            ? v.description
            : v.name.split('/').slice(1).join('/');

          // Check if there are any options (if object is not empty)
          const hasOptions = v.options && Object.keys(v.options).length > 0;
          
          const typeIcons = {
            "dataset/frontend": "🖥️",  // desktop
            "dataset/backend": "🗄️",   // server
            "artifact": "📦",          // optional
          };
          const typeIcon = typeIcons[v.type] || "❓";  // fallback if unknown
          // Render the input field only if options are provided
          return `
            <div class="file">
              <label>
                <input type="checkbox" value="${v.url}" ${v.enabled ? 'checked' : ''}>
                ${typeIcon} ${labelText}
                <a href="${v.url}" target="_blank">[Source]</a>
              </label>
              ${hasOptions ? `
              <br>
              <div class="validator-options-wrapper" style="margin-left: 2.8em;">
                <textarea class="validator-options" data-url="${v.url}">${JSON.stringify(v.options, null, 2)}</textarea>
              </div>
              ` : ''}
            </div>
          `;
        }).join('')}
      `;
    }).join('');
    container.querySelectorAll("textarea.validator-options").forEach(textarea => {
      const resizeToFit = () => {
        textarea.style.height = "auto"; // Reset height
        textarea.style.height = textarea.scrollHeight + "px"; // Adjust to content
      };
    
      // Resize immediately and on input
      resizeToFit();
      textarea.addEventListener("input", resizeToFit);
    });
  }

  async nextIdle() {
    return new Promise(resolve =>
      'requestIdleCallback' in window
        ? requestIdleCallback(resolve)
        : setTimeout(resolve, 0)
    );
  }

  async connectedCallback() {

    const validatorList = this.shadowRoot.querySelector('#validator-list');

    this.textarea = this.shadowRoot.querySelector('#input');
    this.validateBtn = this.shadowRoot.querySelector('#validate');
    this.submitBtn = this.shadowRoot.querySelector('#submit');
    this.output = this.shadowRoot.querySelector('#output');
    this.progressOutput = this.shadowRoot.querySelector("#progress");
    this.validateBtn.addEventListener('click', () => this.runValidation());
    this.submitBtn.addEventListener('click', () => this.postJson());

    // Tab switching: Paste JSON vs Load from URL
    this.inputMode = 'paste';
    const tabPaste = this.shadowRoot.querySelector('#tab-paste');
    const tabUrl = this.shadowRoot.querySelector('#tab-url');
    const urlRow = this.shadowRoot.querySelector('#url-row');
    this.urlInput = this.shadowRoot.querySelector('#url-input');

    tabPaste.addEventListener('click', () => {
      this.inputMode = 'paste';
      tabPaste.classList.add('active');
      tabUrl.classList.remove('active');
      this.textarea.style.display = '';
      urlRow.style.display = 'none';
    });
    tabUrl.addEventListener('click', () => {
      this.inputMode = 'url';
      tabUrl.classList.add('active');
      tabPaste.classList.remove('active');
      this.textarea.style.display = 'none';
      urlRow.style.display = 'flex';
    });

    // Fetch button: load URL content into textarea for preview
    this.shadowRoot.querySelector('#fetch-url').addEventListener('click', async () => {
      const url = this.urlInput.value.trim();
      if (!url) {
        this.output.textContent = '❌ Please enter a URL.';
        return;
      }
      try {
        this.output.textContent = '⏳ Fetching URL…';
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
        const text = await res.text();
        JSON.parse(text); // validate it's JSON
        this.textarea.value = text;
        this.output.textContent = '✅ JSON loaded from URL. Click Validate to proceed.';
      } catch (e) {
        this.output.textContent = `❌ Failed to fetch URL: ${e.message || e}`;
      }
    });

    initPyodide();  // kick off background loading without await

    const default_placeholder = JSON.parse(`
      [
   {
      "messages":[
         {
            "role":"system",
            "content":"You are a helpful assistant."
         },
         {
            "role":"user",
            "content":"Hello, how are you doing today? I hope everything is wonderful."
         },
         {
            "role":"assistant",
            "content":"Hello! I'm doing great, thank you. I hope you're having a wonderful day as well."
         },
         {
            "role":"user",
            "content":"How can I reset my password?"
         },
         {
            "role":"assistant",
            "content":"You can reset your password by clicking on 'Forgot Password' on the login page."
         }
      ]
   },
   {
      "messages":[
         {
            "role":"user",
            "content":"Can you tell me how to reset my password?"
         },
         {
            "role":"assistant",
            "content":"Sure! To reset your password, go to the login page and click on 'Forgot Password'. Follow the instructions to create a new one."
         }
      ]
   }
]
          `);
    this.textarea.value = JSON.stringify(default_placeholder, null, 2);

    const backendUrl = this.getAttribute('validator-source');
    if (backendUrl) {
      validatorList.innerHTML = "📦 Fetching validator list...";
      await this.nextIdle();
      try {
        const res = await fetch(backendUrl + "/list");
        if (!res.ok) throw new Error("Backend API error");

        const validators = await res.json(); // should be an array of ValidatorDetail
        // Optional enrichment or sorting logic can go here
        const enriched = validators.map(v => ({
          name: v.source.split('/').pop(),
          folder: v.source.split('/').slice(-2, -1)[0],
          url: backendUrl + "/raw/" + v.source,
          title: v.title,
          stage: v.stage,
          description: v.description,
          tags: v.tags,
          options: v.options,
          enabled: v.enabled,
          type: v.type,
        }));
    
        this.baseValidatorCode = JSON.parse(await fetch(backendUrl + "/raw/base").then(res => res.text()));

        this.availableValidators = enriched;
        this.renderHierarchicalValidators(validatorList, enriched);
        this.validateBtn.style.display = 'inline-block'
      } catch (e) {
        validatorList.innerHTML = `<p style="color:red;">❌ Failed to fetch: ${e}</p>`;
      }
    }
  }

  onValidationProgress(update) {
    if (!this.progressOutput) {
      console.warn("Progress element not found in shadowRoot");
      return;
    }

    if (update.stage) {
      this.progressOutput.textContent = `Stage: ${update.validator} — ${update.stage}`;
    } else if ("current" in update && "total" in update) {
      this.progressOutput.textContent = `Running: ${update.validator} — ${update.current} / ${update.total}`;
    } else {
      console.log(`[${update.validator}] unknown progress update:`, update);
    }
  }

  async runValidation() {
    this.output.textContent = "⏳ Waiting for Python engine...";
    this.py = await initPyodide();  // waits if still loading

    if (!this._baseLoaded) {
      this.output.textContent = "⏳ Loading base validators...";

      try {
        const fs = this.py.FS;
        if (this.baseValidatorCode) {
          Object.entries(this.baseValidatorCode).forEach(([path, content]) => {
            try {
              if (!path || typeof path !== "string" || typeof content !== "string") {
                console.warn(`⚠️ Skipping invalid entry: ${path}`);
                console.warn(`❌ Invalid content for ${path}`, content);
                return;
              }

              const fileExists = fs.analyzePath(path).exists;
              if (!fileExists) {
                const parentDir = path.split('/').slice(0, -1).join('/');
                if (parentDir && !fs.analyzePath(parentDir).exists) {
                  fs.mkdir(parentDir);
                  console.log(`📁 Created directory: ${parentDir}`);
                }
                fs.writeFile(path, content);
                console.log(`✅ Loaded file: ${path}`);
              } else {
                console.log(`⚠️ Skipped existing file: ${path}`);
              }
            } catch (err) {
              console.error(`❌ Error writing ${path}:`, err);
              throw err; // re-throw to bubble up to your outer catch
            }
          });
        }
        this._baseLoaded = true; // ✅ Prevents re-checking FS next time
      } catch (e) {
        this.output.textContent = `❌ Python exception:\n${e.message || e}`;
        this.submitBtn.style.display = 'none';
        return;
      }
    } 

    this.progressOutput.style.display = "block";
    this.output.textContent = "🚀 Running validation...";

    const checkboxes = this.shadowRoot.querySelectorAll('#validator-list input[type=checkbox]');
    const selectedValidators = [...checkboxes]
      .filter(cb => cb.checked)
      .map(cb => cb.value);

    let data;
    if (this.inputMode === 'url') {
      const url = this.urlInput.value.trim();
      if (!url) {
        this.output.textContent = '❌ Please enter a URL.';
        this.submitBtn.style.display = 'none';
        return;
      }
      try {
        this.output.textContent = '⏳ Fetching dataset from URL…';
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
        const text = await res.text();
        data = JSON.parse(text);
      } catch (e) {
        this.output.textContent = `❌ Failed to load URL: ${e.message || e}`;
        this.submitBtn.style.display = 'none';
        return;
      }
    } else {
      const raw = this.textarea.value;
      try {
        data = JSON.parse(raw);
      } catch (e) {
        this.output.textContent = "❌ Invalid JSON";
        this.submitBtn.style.display = 'none';
        return;
      }
    }

    const results = [];

    let allPassed = true;

    if (!this.loadedValidators) {
      this.loadedValidators = new Set();
    }

    for (const url of selectedValidators) {
      try {
        const validatorMeta = this.availableValidators.find(v => v.url === url);
        const label = validatorMeta?.description || validatorMeta?.name || url;
    
        this.progressOutput.textContent = `Running: ${label}…`;
        await this.nextIdle();  // lets browser update UI
        // Get the options text-area for this validator (using its data-url attribute)
        const optionsInput = this.shadowRoot.querySelector(`textarea.validator-options[data-url="${url}"]`);
        let options = {};
        if (optionsInput) {
          try {
            options = JSON.parse(optionsInput.value);
          } catch (e) {
            console.warn("Invalid JSON in options field, using empty object.");
          }
        }

        const code = await fetch(url + `?t=${Date.now()}`).then(res => res.text()); // disable cache

        // Always clear globals for isolation
        await this.py.runPythonAsync(`
          for name in list(globals()):
              if name not in ('__name__', '__doc__', '__package__', '__loader__', '__spec__', '__annotations__'):
                  del globals()[name]
        `);
        await this.py.runPythonAsync(code);

        this.py.globals.set("progress_callback", (update) => {
          let obj;
          try {
            const asMap = update.toJs ? update.toJs() : update;
            obj = asMap instanceof Map ? Object.fromEntries(asMap) : asMap;
          } catch (e) {
            console.warn("Failed to convert update from Pyodide:", e);
            obj = {};
          }
          this.onValidationProgress(obj);
        });
        await this.py.runPythonAsync(`
                  import inspect
                  import builtins
                  import json
                  from validators.base_validator import BaseValidator

                  # Read options from the injected JSON string
                  import base64 as _b64
                  my_options = json.loads(_b64.b64decode('${btoa(JSON.stringify(options))}').decode())

                  # Collect all subclasses of BaseValidator (excluding BaseValidator itself)
                  candidates = [
                      obj for name, obj in globals().items()
                      if inspect.isclass(obj)
                      and issubclass(obj, BaseValidator)
                      and obj is not BaseValidator
                  ]
                  # Sort by inheritance depth (deepest class first)
                  candidates.sort(key=lambda cls: len(inspect.getmro(cls)), reverse=True)

                  if candidates:
                    validator_class = candidates[0]
                    builtins.__current_validator__ = validator_class(
                        options=my_options,
                        progress_callback=progress_callback
                    )
                  else:
                      raise RuntimeError("❌ No valid subclass of BaseValidator found in global scope.")
                  `);
        this.py.globals.set("input_data", data);
        
        await this.py.runPythonAsync(`
                        import traceback
                        import asyncio
                        import json
                        import builtins
                        async def _run_validate():
                          v = None  # initialize
                          try:
                              global output_result, output_result_json
                              v = __import__('builtins').__current_validator__
                              output_result = await v.validate(input_data)
                          except Exception as e:
                              output_result = {
                                  "status": "failed",
                                  "errors": traceback.format_exc() + str(e),
                                  "validator": v.__class__.__name__ if v else "unknown"
                              }
                          output_result_json = json.dumps(output_result)
                        await _run_validate()
                        `);
        const output = this.py.globals.get("output_result_json");
        console.log(output)
        if (!output) throw new Error("No output from validator");
        const result = JSON.parse(output);
        results.push({ validator: url.split('/').pop(), result });

        // ✅ Simple check: if result contains "failed" or "missing", assume it failed
        const resultStr = JSON.stringify(result).toLowerCase();
        if (
          result.status === "failed" ||
          resultStr.includes('"status":"failed"') ||
          resultStr.includes('"errors":')  // sometimes helpful
        ) {
          allPassed = false;
        }
      } catch (e) {
        allPassed = false;
        results.push({
          validator: url.split('/').pop(),
          result: `❌ Python exception:\n${e.message || e}`
        });
      }
    }
    const formatted = results.map(r => {
      let resText = (typeof r.result === 'string')
        ? r.result
        : JSON.stringify(r.result, null, 2);

      // If it's multiline and not already HTML-formatted, wrap in <pre>
      if (resText.includes('\n') && !resText.includes('<pre>')) {
        resText = `<pre>${resText}</pre>`;
      }

      // Look for a Base64 PNG reference in the result text.
      const pattern = /data:image\/png;base64,[A-Za-z0-9+/=]+/;
      const match = resText.match(pattern);
      if (match) {
        const base64Str = match[0];
        // Replace the Base64 string with an <img> tag.
        resText = resText.replace(pattern, `<br><img src="${base64Str}" alt="Distribution Plot"><br>`);
      }

      // Use <br> for line breaks
      return `🔍 <b>${r.validator}</b>:<br>${resText}`;
    }).join('<br><br>');

    // Use innerHTML to render HTML tags (like <img>) in the output.
    this.output.innerHTML = formatted;
    this.progressOutput.style.display = "none";

    // Render Vega-Lite charts from info items
    if (typeof vegaEmbed !== 'undefined') {
      for (const r of results) {
        const res = r.result;
        if (!res || typeof res !== 'object') continue;
        const infoItems = res.info || [];
        for (const item of infoItems) {
          if (item.chart) {
            const chartEl = document.createElement('div');
            this.output.appendChild(chartEl);
            try {
              await vegaEmbed(chartEl, item.chart, { actions: false });
            } catch (e) {
              chartEl.textContent = `Chart render error: ${e.message}`;
            }
          }
        }
      }
    }
    
    // Show submit button only if all validations passed
    this.submitBtn.style.display = allPassed ? 'inline-block' : 'none';
    
    // Store the data to use for submission
    this.validatedData = data;
  }

  async postJson() {
    const url = this.getAttribute('submit-url');
    if (!url || !this.validatedData) {
      this.output.textContent = "❌ Submit URL missing or no valid data.";
      return;
    }

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.validatedData)
      });

      const text = await res.text();
      this.output.textContent = `✅ Submitted!\nResponse:\n${text}`;
    } catch (e) {
      this.output.textContent = `❌ Submit failed: ${e}`;
    }
  }
}

customElements.define('json-validator', JsonValidator);
