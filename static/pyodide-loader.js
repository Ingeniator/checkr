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

      // Here is list packages included with pyodide https://pyodide.org/en/stable/usage/packages-in-pyodide.html
      // These packages can be loaded with pyodide.loadPackage()
      await py.loadPackage(["pydantic"])

      // Pure Python packages with wheels on PyPI can be loaded directly from PyPI with micropip.install()
      // await py.loadPackage("micropip");
      // await py.runPythonAsync(`
      //   import micropip
      //   #await micropip.install("https://your-server/path/to/your_package_name-0.1.0-py3-none-any.whl")
      // `);
      return py;
    });
  }
  return pyodideReady;
}
