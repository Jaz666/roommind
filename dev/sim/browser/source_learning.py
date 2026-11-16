"""Browser checks for source sensor selectors and bounded preheat configuration."""

from pathlib import Path

from playwright.sync_api import sync_playwright

bundle = (Path(__file__).resolve().parents[3] / "custom_components/roommind/frontend/roommind-panel.js").read_text()
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    for width in [390, 1200]:
        page = browser.new_page(viewport={"width": width, "height": 1000})
        errors = []
        page.on("pageerror", lambda e, found=errors: found.append(str(e)))
        page.route(
            "http://roommind.test/**",
            lambda route: route.fulfill(
                content_type="text/javascript" if route.request.url.endswith(".js") else "text/html",
                body=bundle
                if route.request.url.endswith(".js")
                else '<html><script type="module" src="/panel.js"></script></html>',
            ),
        )
        page.goto("http://roommind.test/")
        page.wait_for_function("!!customElements.get('rs-sensor-section')")
        page.evaluate("""async () => {
          const hass={language:'en',states:{},entities:{},areas:{living:{area_id:'living',name:'Living Room'}},config:{unit_system:{temperature:'°C'}}};
          const settings=document.createElement('rs-settings-sensors'),events=[];
          settings.hass=hass;settings.addEventListener('setting-changed',e=>events.push(e.detail));
          document.body.append(settings);await settings.updateComplete;
          const ct=[...settings.shadowRoot.querySelectorAll('ha-entity-picker')].find(e=>e.label.includes('Whole heat pump'));
          if(!ct)throw Error('Missing CT picker');
          ct.dispatchEvent(new CustomEvent('value-changed',{detail:{value:'sensor.heat_pump_consumption_power'}}));
          if(!events.some(e=>e.key==='heatPumpPowerSensor'&&e.value==='sensor.heat_pump_consumption_power'))throw Error('CT selection lost');
          const room=document.createElement('rs-sensor-section'),changes=[];
          room.hass=hass;room.area=hass.areas.living;room.editing=true;room.preheatMaxMinutes=60;
          room.addEventListener('sensor-changed',e=>changes.push(e.detail));document.body.append(room);await room.updateComplete;
          const dehum=[...room.shadowRoot.querySelectorAll('ha-entity-picker')].find(e=>(e.label??'').includes('Dehumidifier power'));
          if(!dehum)throw Error('Missing dehumidifier picker');
          dehum.dispatchEvent(new CustomEvent('value-changed',{detail:{value:'sensor.dehum_power'}}));
          const preheat=[...room.shadowRoot.querySelectorAll('ha-textfield')].find(e=>(e.label??'').includes('Maximum predictive'));
          preheat.value='0';preheat.dispatchEvent(new Event('change'));
          if(!changes.some(e=>e.key==='preheat_max_minutes'&&e.value===0))throw Error('Zero preheat limit lost');
          if(!changes.some(e=>e.key==='dehumidifier_power_sensor'&&e.value==='sensor.dehum_power'))throw Error('Auxiliary input selection lost');
          const compressor=document.createElement('rs-settings-compressor'),changes2=[];
          compressor.hass=hass;compressor.compressorGroups=[{id:'toshiba',name:'Toshiba',members:['climate.ac'],shared_ac_control:true,min_run_minutes:5,min_off_minutes:5}];
          compressor.addEventListener('setting-changed',e=>changes2.push(e.detail));document.body.append(compressor);await compressor.updateComplete;
          const standby=[...compressor.shadowRoot.querySelectorAll('ha-select')].find(e=>(e.label??'').includes('Idle units'));
          if(!standby||standby.value!=='off'||standby.options.length!==2)throw Error('Idle heating options missing');
          standby.dispatchEvent(new CustomEvent('selected',{detail:{value:'minimum_heat'}}));
          if(!changes2.some(e=>e.value?.[0]?.heating_idle_mode==='minimum_heat'))throw Error('Minimum Heat selection lost');
          compressor.remove();settings.remove();room.remove();
        }""")
        assert not errors, errors
        print(f"Viewport {width}: CT input, dehumidifier input, zero predictive lead passed")
        page.close()
    browser.close()
