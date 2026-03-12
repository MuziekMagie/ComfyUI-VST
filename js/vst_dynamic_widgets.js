import { app } from '../../scripts/app.js'

app.registerExtension({
  name: 'vst.dynamic_widgets',

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (nodeData.name === 'VSTParameters') {
      const origOnNodeCreated = nodeType.prototype.onNodeCreated
      nodeType.prototype.onNodeCreated = function () {
        origOnNodeCreated?.apply(this, arguments)
        this.vstWidgets = []
      }

      nodeType.prototype.packDynamicWidgets = function () {
        if (!this.vstWidgets) return
        const values = {}
        for (const w of this.vstWidgets) {
          values[w.name] = w.value
        }
        const jsonWidget = this.widgets.find((w) => w.name === 'dynamic_values_json')
        if (jsonWidget) {
          jsonWidget.value = JSON.stringify(values)
        }
      }

      nodeType.prototype.updateVSTWidgets = function (paramsJson, isConfiguring = false) {
        try {
          this.lastParamsJson = paramsJson
          const parsedData = JSON.parse(paramsJson)

          let paramsArray = []
          if (typeof parsedData === 'object' && parsedData !== null) {
            paramsArray = Object.values(parsedData)
          }

          if (this.vstWidgets && this.vstWidgets.length > 0) {
            for (const w of this.vstWidgets) {
              const idx = this.widgets.indexOf(w)
              if (idx !== -1) this.widgets.splice(idx, 1)
            }
          }
          this.vstWidgets = []

          const jsonWidget = this.widgets.find((w) => w.name === 'dynamic_values_json')
          if (jsonWidget) {
            jsonWidget.type = 'hidden'
            jsonWidget.computeSize = () => [0, -4]
          }

          for (const param of paramsArray) {
            const name = param.name || 'Param'
            let units = param.units ? String(param.units).trim() : ''
            if (units === 'null' || units === 'None') units = ''

            if (param.is_boolean) {
              const widget = this.addWidget('toggle', name, !!param.value, (val) => {
                if (this.packDynamicWidgets) this.packDynamicWidgets()
              })
              if (units) widget.label = `${name} (${units})`
              this.vstWidgets.push(widget)
            } else if (param.is_choice && param.valid_values) {
              const widget = this.addWidget(
                'combo',
                name,
                String(param.value),
                (val) => {
                  if (this.packDynamicWidgets) this.packDynamicWidgets()
                },
                { values: param.valid_values },
              )
              if (units) widget.label = `${name} (${units})`
              this.vstWidgets.push(widget)
            } else {
              const defaultVal = param.value !== undefined ? param.value : 0.0
              let min = param.min ?? 0.0
              let max = param.max ?? 1.0

              let range = max - min
              let step = 0.01
              let precision = 4

              if (range >= 10) {
                step = 1.0
                precision = 2
              } else if (range >= 2) {
                step = 0.1
                precision = 2
              } else {
                step = 0.01
                precision = 2
              }

              const widget = this.addWidget(
                'number',
                name,
                defaultVal,
                (val) => {
                  if (this.packDynamicWidgets) this.packDynamicWidgets()
                },
                { min: min, max: max, step: step, precision },
              )
              if (units) widget.label = `${name} (${units})`
              this.vstWidgets.push(widget)
            }
          }

          this.packDynamicWidgets()
          this.setSize(this.computeSize())
          if (!isConfiguring) app.graph.setDirtyCanvas(true, true)
        } catch (e) {
          console.error('Failed to parse VST parameters for widgets:', e)
        }
      }

      const origOnSerialize = nodeType.prototype.onSerialize
      nodeType.prototype.onSerialize = function (o) {
        origOnSerialize?.apply(this, arguments)
        o.properties = o.properties || {}
        o.properties.vst_params_json = this.lastParamsJson || '[]'
      }

      const origOnConfigure = nodeType.prototype.onConfigure
      nodeType.prototype.onConfigure = function (o) {
        origOnConfigure?.apply(this, arguments)
        if (o.properties && o.properties.vst_params_json) {
          this.updateVSTWidgets(o.properties.vst_params_json, true)
        }
      }
    }
  },

  async setup(app) {
    app.api.addEventListener('executed', ({ detail }) => {
      const { node, output } = detail
      const executedNode = app.graph.getNodeById(node)

      if (executedNode && executedNode.comfyClass === 'VSTLoader') {
        if (output && output.vst_params) {
          const paramsJson = output.vst_params[0]
          const paramsOutputIndex = 1
          const links = executedNode.outputs[paramsOutputIndex].links

          if (links && links.length > 0) {
            for (const linkId of links) {
              const link = app.graph.links[linkId]
              if (link) {
                const targetNode = app.graph.getNodeById(link.target_id)
                if (targetNode && targetNode.updateVSTWidgets) {
                  targetNode.updateVSTWidgets(paramsJson)
                }
              }
            }
          }
        }
      }
    })
  },
})
