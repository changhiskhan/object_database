/**
 * Plot Cell Cell
 */

import {ConcreteCell} from './ConcreteCell';
import {LineFigure} from './LineFigure';
import {GlRenderer} from './GlRenderer';
import {makeDomElt as h} from './Cell';

class DragHelper {
    constructor(startEvent, callback) {
        this.callback = callback;
        this.isTornDown = false;

        this.onMouseMove = this.onMouseMove.bind(this);
        this.onMouseUp = this.onMouseUp.bind(this);

        this.initialPoint = [startEvent.pageX, startEvent.pageY];
        this.lastPoint = [startEvent.pageX, startEvent.pageY];

        window.addEventListener('mousemove', this.onMouseMove);
        window.addEventListener('mouseup', this.onMouseUp);
    }

    onMouseMove(e) {
        let curPt = [e.pageX, e.pageY];
        this.lastPoint = curPt;

        if (e.buttons) {
            this.callback("move", this.initialPoint, this.lastPoint, curPt);
        } else {
            this.callback("end", this.initialPoint, this.lastPoint, curPt);
            this.teardown();
        }
    }

    onMouseUp(e) {
        let curPt = [e.pageX, e.pageY];
        this.callback("end", this.initialPoint, this.lastPoint, curPt);
        this.teardown();
    }

    teardown() {
        if (this.isTornDown) {
            return;
        }

        this.callback("teardown");

        this.isTornDown = true;
        window.removeEventListener('mousemove', this.onMouseMove)
        window.removeEventListener('mouseup', this.onMouseUp)
    }
}


class Packets {
    constructor(requestPacketFun, onAllPacketsLoaded, onPacketLoadFailed) {
        this.requestPacketFun = requestPacketFun;
        this.onAllPacketsLoaded = onAllPacketsLoaded;
        this.onPacketLoadFailed = onPacketLoadFailed;

        this.error = null;

        this.packetIdToData = {};
        this.touchedPacketsIds = {};
        this.requestedPacketIds = {};
        this.unreceivedPackets = 0;

        this.walkAndRequest = this.walkAndRequest.bind(this);
        this.resetTouchedPackets = this.resetTouchedPackets.bind(this);
        this.eraseUntouched = this.eraseUntouched.bind(this);
        this.requestPacketId = this.requestPacketId.bind(this);

        this.onPacket = this.onPacket.bind(this);
        this.onFailure = this.onFailure.bind(this);

        this.decode = this.decode.bind(this);
        this.decodeNumberOrFloats = this.decodeNumberOrFloats.bind(this);
        this.decodeFloats = this.decodeFloats.bind(this);
        this.decodeColors = this.decodeColors.bind(this);
    }

    resetTouchedPackets() {
        this.touchedPacketsIds = {};
    }

    // get rid of packets we've seen and return whether all mentioned packets are
    // loaded
    eraseUntouched() {
        let toRemove = [];
        for (var packetId in this.packetIdToData) {
            if (!this.touchedPacketsIds[packetId]) {
                toRemove.push(packetId);
            }
        }

        toRemove.forEach(packetId => {
            console.info("Packet " + packetId + " no longer used.");

            delete this.packetIdToData[packetId];

            if (this.requestedPacketIds[packetId]) {
                delete this.requestedPacketIds[packetId];
            }
        });

        for (var packetId in this.touchedPacketsIds) {
            if (!this.packetIdToData[packetId]) {
                return false;
            }
        }

        return true;
    }

    requestPacketId(packetId) {
        this.touchedPacketsIds[packetId] = true;

        if (this.packetIdToData[packetId] !== undefined) {
            return;
        }

        if (this.requestedPacketIds[packetId]) {
            return;
        }

        console.log("Requesting packet " + packetId);

        this.requestedPacketIds[packetId] = true;
        this.unreceivedPackets += 1;

        this.requestPacketFun(packetId, this.onPacket, this.onFailure);
    }

    onPacket(packetId, response) {
        if (!this.requestedPacketIds[packetId]) {
            return;
        }

        this.packetIdToData[packetId] = response;
        delete this.requestedPacketIds[packetId];

        this.unreceivedPackets -= 1;

        if (this.unreceivedPackets == 0) {
            this.onAllPacketsLoaded();
        }
    }

    onFailure(packetId, status, errorText) {
        console.error("Loading " + packetId + " failed: " + errorText);

        this.error = errorText;
        this.onPacketLoadFailed(errorText);
    }

    walkAndRequest(jsonRepresentation) {
        if (!jsonRepresentation) {
            return;
        }

        if (Array.isArray(jsonRepresentation)) {
            jsonRepresentation.forEach(this.walkAndRequest);
            return;
        }

        if (typeof(jsonRepresentation) == 'object') {
            if (jsonRepresentation.packetId) {
                this.requestPacketId(jsonRepresentation.packetId);
            } else {
                for (var key in jsonRepresentation) {
                    this.walkAndRequest(jsonRepresentation[key]);
                }
            }
        }
    }

    decodeNumberOrFloats(jsonRepresentation) {
        if (typeof(jsonRepresentation) == 'number') {
            return jsonRepresentation;
        }

        return new Float32Array(this.packetIdToData[jsonRepresentation.packetId]);
    }

    decodeFloats(jsonRepresentation) {
        return new Float32Array(this.packetIdToData[jsonRepresentation.packetId]);
    }

    decodeColors(jsonRepresentation) {
        if (Array.isArray(jsonRepresentation)) {
            if (jsonRepresentation.length != 4) {
                throw new Error("Bad color encoded");
            }

            return new Float32Array(jsonRepresentation);
        }

        let array = new UInt8Array(this.packetIdToData[jsonRepresentation.packetId]);
        let floats = new Float32Array(new ArrayBuffer(4 * array.length));

        for (let i = 0; i < array.length; i++) {
            floats[i] = array[i] / 255.0;
        }

        return new Float32Array(this.packetIdToData[jsonRepresentation.packetId]);
    }

    decode(jsonRepresentation) {
        if (jsonRepresentation.packetId) {
            return this.packetIdToData[jsonRepresentation.packetId];
        }

        return jsonRepresentation;
    }
}


class WebglPlot extends ConcreteCell {
    constructor(props, ...args) {
        super(props, ...args);

        this.installResizeObserver = this.installResizeObserver.bind(this);
        this.loadPacketIfNecessary = this.loadPacketIfNecessary.bind(this);
        this.onPlotDataReceived = this.onPlotDataReceived.bind(this);
        this.drawScene = this.drawScene.bind(this);

        this.requestedPacketId = 0;
        this.loadedPacketId = 0;

        this.onMouseDown = this.onMouseDown.bind(this);
        this.onWheel = this.onWheel.bind(this);
        this.onDoubleclick = this.onDoubleclick.bind(this);

        this.currentDragHelper = null;

        this.animationFrameRequested = false;
        this.requestAnimationFrame = this.requestAnimationFrame.bind(this);
        this.onPacketLoadFailed = this.onPacketLoadFailed.bind(this);
        this.lineFigureFromJson = this.lineFigureFromJson.bind(this);

        this.renderedDefaultViewport = null;

        this.packets = new Packets(
            this.requestPacket,
            this.loadPacketIfNecessary,
            this.onPacketLoadFailed
        );

        this.figures = [];
    }

    requestAnimationFrame() {
        if (this.animationFrameRequested) {
            return;
        }

        this.animationFrameRequested = true;

        window.requestAnimationFrame(() => {
            this.animationFrameRequested = false;

            this.drawScene();
        })
    }

    onPacketLoadFailed(error) {
        console.error("TODO: set the screen to an error display");
    }

    drawScene() {
        if (!this.props.plotData) {
            return;
        }

        let arraysEqual = (x, y) => {
            if (!x && !y) {
                return true;
            }
            if (!x || !y) {
                return false;
            }

            if (x.length != y.length) {
                return false;
            }

            for (let i = 0; i < x.length; i++) {
                if (x[i] != y[i]) {
                    return false;
                }
            }
            return true;
        }

        if (!arraysEqual(this.props.plotData.defaultViewport, this.renderedDefaultViewport)) {
            this.renderer.scrollToRectangle(this.props.plotData.defaultViewport);
            this.renderedDefaultViewport = this.props.plotData.defaultViewport;
        }

        if (this.props.plotData.backgroundColor) {
            this.renderer.clearViewport(
                this.props.plotData.backgroundColor
            )
        } else {
            this.renderer.clearViewport(
                [0.0, 0.0, 0.0, 1.0]
            )
        }

        this.figures.forEach(figure => {
            figure.drawSelf(this.renderer)
        })
    }

    _computeFillSpacePreferences() {
        return {horizontal: true, vertical: true};
    }

    onWheel(e) {
        e.preventDefault();

        let rect = this.canvas.getBoundingClientRect();

        let xFrac = (e.pageX - rect.left) / rect.width;
        let yFrac = (rect.height - (e.pageY - rect.top)) / rect.height;

        this.renderer.zoom(xFrac, yFrac, Math.exp(e.deltaY / 100))

        this.requestAnimationFrame();
    }

    onDoubleclick(e) {
        if (this.renderedDefaultViewport) {
            this.renderer.scrollToRectangle(this.renderedDefaultViewport);
            this.requestAnimationFrame();
        }
    }

    onMouseDown(e) {
        e.preventDefault();

        if (this.currentDragHelper) {
            this.currentDragHelper.teardown();
        }

        if (e.ctrlKey) {
            // we are panning
            this.currentDragHelper = new DragHelper(e,
                (event, startPoint, lastPoint,  curPoint) => {
                    if (event == "teardown") {
                        return;
                    }

                    this.renderer.scrollPixels(
                        -(curPoint[0] - lastPoint[0]) / this.canvas.width,
                        (curPoint[1] - lastPoint[1]) / this.canvas.height
                    );

                    this.requestAnimationFrame();

                    if (event == 'end') {
                        this.currentDragHelper = null;
                    }
                }
            );
        } else {
            // we are selecting a zoom region
            let hasMoved = false;

            this.currentDragHelper = new DragHelper(e,
                (event, startPoint, lastPoint,  curPoint) => {
                    if (event == "teardown") {
                        this.currentDragHelper = null;
                        return;
                    }

                    let curRect = this.canvas.getBoundingClientRect();

                    if (Math.abs(startPoint[0] - curPoint[0]) + Math.abs(startPoint[1] - curPoint[1]) > 10) {
                        hasMoved = true;
                    }

                    if (!hasMoved) {
                        return;
                    }

                    if (event == "teardown" || event == "end") {
                        this.dragDiv.setAttribute("style", "height:0px; width: 0px; display: none");

                        if (event == "end") {
                            let x0 = startPoint[0] - curRect.left;
                            let y0 = this.canvas.height - (startPoint[1] - curRect.top);

                            let x1 = curPoint[0] - curRect.left;
                            let y1 = this.canvas.height - (curPoint[1] - curRect.top);

                            this.renderer.zoomRect(
                                x0 / this.canvas.width,
                                y0 / this.canvas.height,
                                x1 / this.canvas.width,
                                y1 / this.canvas.height
                            )

                            this.requestAnimationFrame();
                        }
                    } else {
                        let [x0, y0] = startPoint;
                        let [x1, y1] = curPoint;

                        if (x0 > x1) {
                            [x0, x1] = [x1, x0];
                        }
                        if (y0 > y1) {
                            [y0, y1] = [y1, y0];
                        }

                        x0 -= curRect.left;
                        y0 -= curRect.top;
                        x1 -= curRect.left;
                        y1 -= curRect.top;

                        this.dragDiv.setAttribute("style",
                            "height:" + (y1 - y0) + "px;" +
                            "width:" + (x1 - x0) + "px;" +
                            "left:" + x0 + "px;" +
                            "top:" + y0 + "px;" +
                            "position:absolute;"
                        )
                    }
                }
            );
        }
    }

    build() {
        this.canvas = h(
            'canvas', {
                style: 'width:100%;height:100%',
                onmousedown: this.onMouseDown,
                onwheel: this.onWheel,
                ondblclick: this.onDoubleclick
            },
            ["Error: no WEBGL available"]
        );

        this.dragDiv = h(
            'div', {
                style: 'width:0px;height:0px;display:none',
                class: "plot-zoom-handle"
            }, []
        );

        this.loadPacketIfNecessary();

        return h('div', {}, [this.canvas, this.dragDiv]);
    }

    rebuildDomElement() {
        this.loadPacketIfNecessary();
    }

    loadPacketIfNecessary() {
        // this.props.plotData is a structure with {packetId: int} inside in various places
        // we need to walk the json and find out if we have any packets we have yet to request
        // and clear out any ones that are not represented here
        this.packets.resetTouchedPackets();
        this.packets.walkAndRequest(this.props.plotData);

        if (this.packets.eraseUntouched()) {
            // we can rebuild our plot now
            this.figures = [];

            if (this.props.plotData) {
                this.props.plotData.figures.forEach(figureJson => {
                    if (figureJson.type == 'LineFigure') {
                        this.figures.push(
                            this.lineFigureFromJson(figureJson)
                        );
                    }
                });
            }

            this.requestAnimationFrame();
        }
    }

    lineFigureFromJson(figureJson) {
        let xs = this.packets.decodeFloats(figureJson.x);
        let ys = this.packets.decodeFloats(figureJson.y);

        let lineWidth = this.packets.decodeNumberOrFloats(figureJson.lineWidth);
        let color = this.packets.decodeColors(figureJson.color);

        return new LineFigure(
            xs,
            ys,
            lineWidth,
            color
        );
    }

    onPlotDataReceived(packetId, plotData) {
        if (this.loadedPacketId >= packetId) {
            return;
        }

        console.log("Packet " + packetId + " received in "
            + (Date.now() - this.packetRequestedAt) + " milliseconds.");

        this.loadedPacketId = packetId;
        this.lines = new LineFigure(
            new Float32Array(plotData),
            this.props.lineWidth
        );

        this.requestAnimationFrame();
    }

    cellWillUnload() {
        try {
            // release opengl memory
            this.renderer.gl.getExtension('WEBGL_lose_context').loseContext();
        } catch(e) {
            console.error(e);
        }
    }

    installResizeObserver() {
        let observer = new ResizeObserver(entries => {
            for (let entry of entries) {
                if (entry.contentRect.width == this.lastWidth &&
                    entry.contentRect.height == this.lastHeight) {
                    return
                }

                this.lastWidth = entry.contentRect.width;
                this.lastHeight = entry.contentRect.height;
            }

            this.canvas.width = this.lastWidth;
            this.canvas.height = this.lastHeight;

            this.drawScene();
        });

        observer.observe(this.domElement);
    }

    onFirstInstalled() {
        this.canvas.width = this.canvas.clientWidth;
        this.canvas.height = this.canvas.clientHeight;

        this.renderer = new GlRenderer(this.canvas);

        this.installResizeObserver();
        this.requestAnimationFrame();
    }
}

export {WebglPlot, WebglPlot as default};
