"""Browser checks for tariff settings, native fields, and room-selection events."""

from pathlib import Path

from playwright.sync_api import sync_playwright

bundle = (Path(__file__).resolve().parents[3] / "custom_components/roommind/frontend/roommind-panel.js").read_text()
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    for width in [390, 1200]:
        page = browser.new_page(viewport={"width": width, "height": 1000})
        errors = []
        page.on("pageerror", lambda e, page_errors=errors: page_errors.append(str(e)))
        page.route(
            "http://roommind.test/**",
            lambda route: route.fulfill(
                content_type="text/javascript" if route.request.url.endswith(".js") else "text/html",
                body=bundle
                if route.request.url.endswith(".js")
                else '<html><body><script type="module" src="/panel.js"></script></body></html>',
            ),
        )
        page.goto("http://roommind.test/")
        page.wait_for_function("!!customElements.get('rs-settings-tariff')")
        result = page.evaluate("""async () => {
          const el=document.createElement('rs-settings-tariff'),events=[];
          el.hass={language:'en',config:{unit_system:{temperature:'°C'}},areas:{living:{name:'Living Room'}}};
          el.rooms={living:{temperature_sensor:'sensor.external',devices:[{type:'ac',entity_id:'climate.ac'}]},radiator:{temperature_sensor:'sensor.other',devices:[{type:'trv'}]},managed:{devices:[{type:'ac'}]}};
          el.addEventListener('setting-changed',e=>{events.push(e.detail);el[e.detail.key]=e.detail.value;});document.body.append(el);await el.updateComplete;
          const change=(input,value)=>{input.value=value;input.dispatchEvent(new Event('change'));};
          const switches=el.shadowRoot.querySelectorAll('ha-switch');
          if(!switches[1].disabled)throw Error('Boost enabled without tariff');
          switches[0].checked=true;switches[0].dispatchEvent(new Event('change'));await el.updateComplete;
          if(switches[1].disabled)throw Error('Boost not enabled with tariff');
          const times=el.shadowRoot.querySelectorAll('input[type=time]');
          if(times[0].value!=='00:00'||times[1].value!=='05:00')throw Error('Wrong GMT defaults');
          const nums=el.shadowRoot.querySelectorAll('input[type=number]');change(nums[0],'45');change(nums[1],'0');await el.updateComplete;
          if(el.acMorningBoostStopMargin!==0||el.acMorningBoostMinutes!==45)throw Error('Numeric edits missing');
          const boxes=el.shadowRoot.querySelectorAll('input[type=checkbox]');if(boxes.length!==1)throw Error('Ineligible rooms selectable');
          boxes[0].checked=true;boxes[0].dispatchEvent(new Event('change'));await el.updateComplete;
          if(el.acMorningBoostRooms[0]!=='living')throw Error('Room not selected');
          el.hass={...el.hass,config:{unit_system:{temperature:'°F'}}};el.acMorningBoostStopMargin=0.2;await el.updateComplete;
          if(Math.abs(Number(el.shadowRoot.querySelectorAll('input[type=number]')[1].value)-0.36)>0.001)throw Error('Bias incorrectly converted as absolute temperature');
          if(!el.shadowRoot.textContent.includes('GMT / UTC'))throw Error('Timezone guidance missing');
          if(document.documentElement.scrollWidth>window.innerWidth)throw Error('Mobile overflow');
          return 'GMT fields, heat-only tariff toggle, boost gating, zero stop margin, eligible rooms, Fahrenheit delta';
        }""")
        page.evaluate("""async () => {
          const hass={language:'en',states:{},config:{unit_system:{temperature:'°C'}},user:{name:'Test'}};
          for(const tag of ['rs-hero-status','rs-area-card']) {
            const el=document.createElement(tag);el.hass=hass;el.area={area_id:'living',name:'Living Room'};document.body.append(el);
            for(const [status,label] of [['peak','AC heat locked (peak)'],['boost','Morning boost'],['warmth_hold','Morning warmth']]) {
              el.climateControlActive=true;
              el.config={devices:[{entity_id:'climate.ac',type:'ac'}],temperature_sensor:'sensor.external',climate_mode:'auto',live:{current_temp:19,current_humidity:50,target_temp:21,heat_target:21,cool_target:21.5,mode:'idle',heating_power:0,device_setpoint:null,override_active:false,ac_tariff_status:status}};
              await el.updateComplete;
              if(!el.shadowRoot.textContent.includes(label))throw Error(tag+' missing '+label);
              el.climateControlActive=false;await el.updateComplete;
              if(el.shadowRoot.textContent.includes(label))throw Error('Disabled control claims tariff protection');
            }
            el.remove();
          }
        }""")
        assert not errors, errors
        print(f"Viewport {width}: {result}")
        if width == 390:
            page.screenshot(path="/tmp/roommind-tariff-settings-mobile.png", full_page=True)
        page.close()
    browser.close()
