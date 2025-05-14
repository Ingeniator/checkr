let pyodideReady;

export async function initPyodide() {
  if (!pyodideReady) {
    pyodideReady = loadPyodide().then(async (py) => {
      // define safe fetch to use in python code
      globalThis.safeFetch = async function (url) {
        try {
          const res = await fetch(url);
          return { ok: res.ok, status: res.status };
        } catch (err) {
          return {
            ok: false,
            status: 0,
            error: err?.message || "network error"
          };
        }
      };
      await py.loadPackage("micropip");
      await py.runPythonAsync(`
        import micropip
        #await micropip.install("https://your-server/path/to/your_package_name-0.1.0-py3-none-any.whl")
        await micropip.install("pytz>=2024.2", keep_going=True)
        await micropip.install("pydantic<2.0", keep_going=True)
      `);
      return py;
    });
  }
  return pyodideReady;
}
