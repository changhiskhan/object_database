/*
 * Tests for Message Handling in CellHandler
 */
require('jsdom-global')();
const maquette = require('maquette');
const h = maquette.h;
const CellHandler = require('../../CellHandler.js').default;
const chai = require('chai');
const assert = chai.assert;
let projector = maquette.createProjector();
const registry = require('../../ComponentRegistry').ComponentRegistry;
const Point = require('../util/SheetUtils.js').Point;
const Frame = require('../util/SheetUtils.js').Frame;
const CompositeFrame = require('../util/SheetUtils.js').CompositeFrame;
const DataFrame = require('../util/SheetUtils.js').DataFrame;
const SelectionFrame = require('../util/SheetUtils.js').SelectionFrame;


/* Example Messages and Structures */
let simpleRoot = {
    id: "page_root",
    cellType: "RootCell",
    parentId: null,
    nameInParent: null,
    extraData: {},
    namedChildren: {}
};

let simpleSheet = {
    id: 6,
    cellType: "Sheet",
    extraData: {dontFetch: true},
    namedChildren: {}
};

let makeUpdateMessage = (compDescription) => {
    return Object.assign({}, compDescription, {
        channel: "#main",
        type: "#cellUpdated",
        shouldDisplay: true
    });
};

let makeCreateMessage = (compDescription) => {
    return Object.assign({}, compDescription, {
        channel: "#main",
        type: "#cellUpdated",
        shouldDisplay: true
    });
};

let makeDiscardedMessage = (compDescription) => {
    return Object.assign({}, compDescription, {
        channel: "#main",
        type: "#cellDiscarded"
    });
};

describe("Sheet util tests.", () => {
    describe("Point class tests.", () => {
        before(() => {
        });
        after(() => {
        });
        it("Getters", () => {
            let p = new Point([10, 20]);
            assert.equal(p.x, 10);
            assert.equal(p.y, 20);
        });
        it("Setters", () => {
            let p = new Point();
            p.x = 0;
            p.y = 1;
            assert.equal(p.x, 0);
            assert.equal(p.y, 1);
        });
        it("Copy", () => {
            let p = new Point([10, 20]);
            let pCopy = p.copy;
            assert.equal(p.x, 10);
            assert.equal(p.y, 20);
            assert.equal(pCopy.x, 10);
            assert.equal(pCopy.y, 20);
            pCopy.x = 100;
            pCopy.y = 200;
            assert.equal(p.x, 10);
            assert.equal(p.y, 20);
            assert.equal(pCopy.x, 100);
            assert.equal(pCopy.y, 200);
        });
        it("Equals", () => {
            let p = new Point([0, 0]);
            assert.isTrue(p.equals(p));
            let another_p = new Point([0, 0]);
            assert.isTrue(p.equals(another_p));
            another_p = new Point([1, 0]);
            assert.isFalse(p.equals(another_p));
        });
        it("String representation", () => {
            let p = new Point([10, 20]);
            assert.equal(p.toString(), "10,20");
            p = new Point();
            assert.equal(p.toString(), "NaN");
        });
        it("isNaN", () => {
            let p = new Point();
            assert.isTrue(p.isNaN);
            p = new Point(null);
            assert.isTrue(p.isNaN);
            p = new Point(undefined);
            assert.isTrue(p.isNaN);
            p = new Point([0, 0]);
            assert.isFalse(p.isNaN);
            p = new Point([1, 0]);
            assert.isFalse(p.isNaN);
            p = new Point([0, 1]);
            assert.isFalse(p.isNaN);
            p = new Point([1, 1]);
            assert.isFalse(p.isNaN);
        });
        it("Quadrant", () => {
            let p = new Point([1, 1]);
            assert.equal(p.quadrant, 1);
            p = new Point([1, -1]);
            assert.equal(p.quadrant, 2);
            p = new Point([-1, -1]);
            assert.equal(p.quadrant, 3);
            p = new Point([-1, 1]);
            assert.equal(p.quadrant, 4);
        });
        it("Quadrant (edge cases)", () => {
            let p = new Point([0, 0]);
            assert.equal(p.quadrant, 1);
            p = new Point([0, -1]);
            assert.equal(p.quadrant, 2);
            p = new Point([-1, 0]);
            assert.equal(p.quadrant, 3);
        });
        it("Translate", () => {
            let p = new Point([10, 20]);
            p.translate(new Point([1, 2]));
            assert.equal(p.x, 11);
            assert.equal(p.y, 22);
            p.translate([1, 2]);
            assert.equal(p.x, 12);
            assert.equal(p.y, 24);
        });
    });
    describe("Frame class tests.", () => {
        before(() => {
        });
        after(() => {
        });
        it("Name", () => {
            let frame = new Frame([0, 0], [9, 19], name="myframe");
            assert.equal(frame.name, "myframe");
            frame = new Frame([0, 0], [9, 19]);
            frame.setName = "myname";
            assert.equal(frame.name, "myframe");
        });
        it("Dimension", () => {
            let frame = new Frame([0, 0], [9, 19]);
            assert.equal(frame.dim, 2);
            assert.isFalse(isNaN(frame.dim));
        });
        it("Dimension of single point frame", () => {
            let frame = new Frame([0, 0], [0, 0]);
            assert.equal(frame.dim, 0);
            assert.isFalse(isNaN(frame.dim));
        });
        it("Dimension of empty frame", () => {
            frame = new Frame();
            assert.isTrue(isNaN(frame.dim));
            frame = new Frame([0, 0], undefined);
            assert.isTrue(isNaN(frame.dim));
            frame = new Frame(undefined, [0, 0]);
            assert.isTrue(isNaN(frame.dim));
        });
        it("Size", () => {
            var frame = new Frame([1, 5], [5, 7]);
            assert.equal(frame.size.x, 4);
            assert.equal(frame.size.y, 2);
        });
        it("Size of empty frame", () => {
            var frame = new Frame();
            assert.isTrue(isNaN(frame.size));
            frame = new Frame([0, 0], undefined);
            assert.isTrue(isNaN(frame.size));
            frame = new Frame(undefined, [0, 0]);
            assert.isTrue(isNaN(frame.size));
        });
        it("Equality", () => {
            let frame = new Frame([0, 0], [1, 1]);
            assert.isTrue(frame.equals(frame));
            let another_frame = new Frame([0, 0], [1, 1]);
            assert.isTrue(frame.equals(another_frame));
            another_frame = new Frame([0, 0], [2, 2]);
            assert.isFalse(frame.equals(another_frame));
        });
        it("Invalid dimension frame (negative coordinates)", () => {
            try {
                let frame = new Frame([0, 0], [-1, 0]);
            } catch(e) {
                assert.equal(e,"Both 'origin' and 'corner' must be of non-negative coordinates");
            }
            try {
                let frame = new Frame([-1, 0], [1, 0]);
            } catch(e) {
                assert.equal(e,"Both 'origin' and 'corner' must be of non-negative coordinates");
            }
        });
        it("Invalid dimension frame (reversed corner and origin)", () => {
            try {
                let frame = new Frame([1, 1], [0, 0]);
            } catch(e) {
                assert.equal(e,"Origin must be top-left and corner bottom-right");
            }
        });
        it("Is empty", () => {
            frame = new Frame();
            assert.isTrue(frame.empty);
        });
        it("Setting a new origin", () => {
            let frame = new Frame([0, 0], [7, 9]);
            assert.equal(frame.origin.x, 0);
            assert.equal(frame.origin.y, 0);
            frame.setOrigin = [5, 7];
            assert.equal(frame.origin.x, 5);
            assert.equal(frame.origin.y, 7);
            let coords = [];
            for (let x = 5; x <= 7; x++){
                for (let y = 7; y <= 9; y++){
                    coords.push(new Point([x, y]));
                }
            }
            assert.equal(coords.length, frame.coords.length);
            let coordinateStr = coords.map((item) => {return item.toString();});
            let frameCoordinateStr = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coordinateStr.length; i++){
                assert.isTrue(frameCoordinateStr.includes(coordinateStr[i]));
            }
        });
        it("Setting a new corner", () => {
            let frame = new Frame([5, 7], [9, 9]);
            assert.equal(frame.corner.x, 9);
            assert.equal(frame.corner.y, 9);
            frame.setCorner = [7, 9];
            assert.equal(frame.corner.x, 7);
            assert.equal(frame.corner.y, 9);
            let coords = [];
            for (let x = 5; x <= 7; x++){
                for (let y = 7; y <= 9; y++){
                    coords.push(new Point([x, y]));
                }
            }
            assert.equal(coords.length, frame.coords.length);
            let coords_str = coords.map((item) => {return item.toString();});
            let frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
        });
        it("Coords", () => {
            let frame = new Frame([5, 7], [7, 9]);
            let coords = [];
            for (let x = 5; x <= 7; x++){
                for (let y = 7; y <= 9; y++){
                    coords.push(new Point([x, y]));
                }
            }
            assert.equal(coords.length, frame.coords.length);
            let coords_str = coords.map((item) => {return item.toString();});
            let frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
        });
        it("Contaiment (array)", () => {
            let frame = new Frame([0, 0], [10, 10]);
            assert.isTrue(frame.contains([5, 5]));
            assert.isFalse(frame.contains([15, 15]));
            assert.isFalse(frame.contains([-5, 5]));
        });
        it("Contaiment (string rep)", () => {
            let frame = new Frame([0, 0], [10, 10]);
            assert.isTrue(frame.contains("5,5"));
            assert.isFalse(frame.contains("15, 15"));
            assert.isFalse(frame.contains("-5, 5"));
        });
        it("Contaiment (point)", () => {
            let frame = new Frame([0, 0], [10, 10]);
            let point = new Point([1, 1]);
            assert.isTrue(frame.contains(point));
            point = new Point([15, 15]);
            assert.isFalse(frame.contains(point));
        });
        it("Contaiment (frame)", () => {
            let frame = new Frame([0, 0], [10, 10]);
            let another_frame = new Frame([1, 1], [9, 9]);
            assert.isTrue(frame.contains(another_frame));
            another_frame = new Frame([0, 0], [10, 10]);
            assert.isTrue(frame.contains(another_frame));
            another_frame = new Frame([1, 1], [19, 19]);
            assert.isFalse(frame.contains(another_frame));
            another_frame = new Frame([11, 11], [19, 19]);
            assert.isFalse(frame.contains(another_frame));
        });
        it("Contaiment (exception)", () => {
            let frame = new Frame([0, 0], [10, 10]);
            try {
                frame.contains("NOT A POINT");
            } catch(e) {
                assert.equal(e, "You must pass a length 2 array, a Point, or a Frame");
            }
        });
        it("Coords of empty frame", () => {
            let frame = new Frame();
            assert.equal(0, frame.coords.length);
        });
        it("Coords slice", () => {
            // x-axis
            let frame = new Frame([0, 0], [10, 10]);
            let slice_x = [];
            for (let x = 0; x <= 10; x++){
                slice_x.push(new Point([x, 5]));
            }
            let slice_x_str = slice_x.map((item) => {return item.toString();});
            let frame_slice_x_str = frame.sliceCoords(5, "x").map((item) => {return item.toString();});
            assert.equal(slice_x.length, frame_slice_x_str.length);
            for (let i = 0; i < slice_x_str.length; i++){
                assert.isTrue(frame_slice_x_str.includes(slice_x_str[i]));
            }
            // y-axis
            let slice_y = [];
            for (let y = 0; y <= 10; y++){
                slice_y.push(new Point([5, y]));
            }
            assert.equal(slice_x.length, frame.sliceCoords(5, "y").length);
            let slice_y_str = slice_y.map((item) => {return item.toString();});
            let frame_slice_y_str = frame.sliceCoords(5, "y").map((item) => {return item.toString();});
            for (let i = 0; i < slice_y_str.length; i++){
                assert.isTrue(frame_slice_y_str.includes(slice_y_str[i]));
            }
        });
        it("Coords slice (empty)", () => {
            let frame = new Frame([0, 0], [10, 10]);
            try {
                frame.sliceCoords(100, "x");
            } catch(e){
                assert.equal(e, "Index out of range");
            }
            try {
                frame.sliceCoords(100, "y");
            } catch(e){
                assert.equal(e, "Index out of range");
            }
        });
        it("Translate up right", () => {
            let frame = new Frame([3, 4], [5, 6]);
            assert.equal(frame.dim, 2);
            let coords = [];
            for (let x = 3; x <= 5; x++){
              for (let y = 4; y <= 6; y++){
                  coords.push(new Point([x, y]));
              }
            }
            assert.equal(coords.length, frame.coords.length);
            let coords_str = coords.map((item) => {return item.toString();});
            let frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
            // now translate
            frame.translate([2, 3]);
            assert.equal(frame.dim, 2);
            coords = [];
            for (let x = 5; x <= 7; x++){
              for (let y = 7; y <= 9; y++){
                  coords.push(new Point([x, y]));
              }
            }
            assert.equal(coords.length, frame.coords.length);
            coords_str = coords.map((item) => {return item.toString();});
            frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
        });
        it("Translate none", () => {
            let frame = new Frame([3, 4], [5, 6]);
            assert.equal(frame.dim, 2);
            let coords = [];
            for (let x = 3; x <= 5; x++){
              for (let y = 4; y <= 6; y++){
                  coords.push(new Point([x, y]));
              }
            }
            assert.equal(coords.length, frame.coords.length);
            let coords_str = coords.map((item) => {return item.toString();});
            let frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
            // now translate
            frame.translate([0, 0]);
            assert.equal(frame.dim, 2);
            assert.equal(coords.length, frame.coords.length);
            coords_str = coords.map((item) => {return item.toString();});
            frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
        });
        it("Translate down left", () => {
            let frame = new Frame([3, 4], [5, 6]);
            assert.equal(frame.dim, 2);
            let coords = [];
            for (let x = 3; x <= 5; x++){
              for (let y = 4; y <= 6; y++){
                  coords.push(new Point([x, y]));
              }
            }
            assert.equal(coords.length, frame.coords.length);
            let coords_str = coords.map((item) => {return item.toString();});
            let frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
            // now translate
            frame.translate([-1, -1]);
            coords = [];
            for (let x = 2; x <= 4; x++){
              for (let y = 3; y <= 5; y++){
                  coords.push(new Point([x, y]));
              }
            }
            assert.equal(frame.dim, 2);
            assert.equal(coords.length, frame.coords.length);
            coords_str = coords.map((item) => {return item.toString();});
            frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
        });
        it("Translate (not in place)", () => {
            let frame = new Frame([3, 4], [5, 6]);
            assert.equal(frame.dim, 2);
            let coords = [];
            for (let x = 3; x <= 5; x++){
              for (let y = 4; y <= 6; y++){
                  coords.push(new Point([x, y]));
              }
            }
            assert.equal(coords.length, frame.coords.length);
            let coords_str = coords.map((item) => {return item.toString();});
            let frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
            // now translate
            frame = frame.translate([-1, -1], inplace=false);
            coords = [];
            for (let x = 2; x <= 4; x++){
              for (let y = 3; y <= 5; y++){
                  coords.push(new Point([x, y]));
              }
            }
            assert.equal(frame.dim, 2);
            assert.equal(coords.length, frame.coords.length);
            coords_str = coords.map((item) => {return item.toString();});
            frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
        });
        it("Translate out of quadrant 1", () => {
            let frame = new Frame([3, 4], [5, 6]);
            assert.equal(frame.dim, 2);
            let coords = [];
            for (let x = 3; x <= 5; x++){
              for (let y = 4; y <= 6; y++){
                  coords.push(new Point([x, y]));
              }
            }
            assert.equal(coords.length, frame.coords.length);
            let coords_str = coords.map((item) => {return item.toString();});
            let frame_coords_str = frame.coords.map((item) => {return item.toString();});
            for (let i = 0; i < coords_str.length; i++){
                assert.isTrue(frame_coords_str.includes(coords_str[i]));
            }
            // now translate
            try {
                frame.translate([-10, -1]);
            } catch(e){
                assert.equal(e, "Invalid translation: new 'origin' and 'corner' must be of non-negative coordinates");
            }
        });
        it("Intersect (arrangement A)", () => {
            let frame = new Frame([0, 0], [10, 10]);
            // basic overlap
            let another_frame = new Frame([5, 5], [15, 15]);
            let intersection = frame.intersect(another_frame);
            assert.exists(intersection);
            let test_intersection = new Frame([5, 5], [10, 10]);
            assert.isTrue(intersection.equals(test_intersection));
            // contained
            another_frame = new Frame([1, 1], [9, 9]);
            intersection = frame.intersect(another_frame);
            assert.exists(intersection);
            test_intersection = new Frame([1, 1], [9, 9]);
            assert.isTrue(intersection.equals(test_intersection));
            // not contained
            another_frame = new Frame([11, 11], [19, 19]);
            intersection = frame.intersect(another_frame);
            assert.exists(intersection);
            assert.isTrue(intersection.empty);
        });
        it("Intersect (arrangement B)", () => {
            let frame = new Frame([10, 10], [20, 20]);
            // basic overlap
            let another_frame = new Frame([0, 0], [15, 15]);
            let intersection = frame.intersect(another_frame);
            assert.exists(intersection);
            let test_intersection = new Frame([10, 10], [15, 15]);
            assert.isTrue(intersection.equals(test_intersection));
            // contained
            another_frame = new Frame([11, 11], [19, 19]);
            intersection = frame.intersect(another_frame);
            assert.exists(intersection);
            test_intersection = new Frame([11, 11], [19, 19]);
            assert.isTrue(intersection.equals(test_intersection));
            // not contained
            another_frame = new Frame([0, 0], [5, 5]);
            intersection = frame.intersect(another_frame);
            assert.exists(intersection);
            assert.isTrue(intersection.empty);
        });
        it("Intersect (empty frame)", () => {
            let frame = new Frame([0, 0], [10, 10]);
            let another_frame = new Frame();
            let intersection = frame.intersect(another_frame);
            assert.isTrue(intersection.empty);
            frame = new Frame();
            another_frame = new Frame([0, 0], [10, 10]);
            intersection = frame.intersect(another_frame);
            assert.isTrue(intersection.empty);
        });
        it("Map (not strict)", () => {
            // contained
            let frame = new Frame([0, 0], [10, 10]);
            let anotherFrame = new Frame([5, 4], [9, 10]);
            let mappedFrame = anotherFrame.map(frame, new Point([2, 2]));
            assert.isTrue(mappedFrame.equals(new Frame([2, 2], [6, 8])));
            // not contained
            frame = new Frame([0, 0], [10, 10]);
            anotherFrame = new Frame([5, 4], [20, 20]);
            mappedFrame = anotherFrame.map(frame, new Point([2, 2]));
            assert.isTrue(mappedFrame.equals(new Frame([2, 2], [10, 10])));
        });
        it("Map (strict)", () => {
            // contained
            let frame = new Frame([0, 0], [10, 10]);
            let anotherFrame = new Frame([5, 4], [9, 10]);
            let mappedFrame = anotherFrame.map(frame, new Point([2, 2]), strict=true);
            assert.isTrue(mappedFrame.equals(new Frame([2, 2], [6, 8])));
            // not contained
            frame = new Frame([0, 0], [10, 10]);
            anotherFrame = new Frame([5, 4], [20, 20]);
            mappedFrame = anotherFrame.map(frame, new Point([2, 2]), strict=true);
            assert.isTrue(mappedFrame.equals(new Frame()));
        });
        it("Map (exception)", () => {
            // contained
            let frame = new Frame([0, 0], [10, 10]);
            let anotherFrame = new Frame([5, 4], [9, 10]);
            try {
                let mappedFrame = anotherFrame.map(frame, new Point([20, 30]), strict=true);
            } catch(e) {
                assert.equal(e, "the specified origin is not contained in the provided frame.");
            }
        });
    });
    describe("CompositeFrame class tests.", () => {
        before(() => {
        });
        after(() => {
        });
        it("BaseFrame", () => {
            try {
                new CompositeFrame("a", []);
            } catch(e) {
                assert.equal(e, "baseFrame must be a Frame class object");
            }
            let frame = new DataFrame([0, 0], [10, 10]);
            assert.isTrue(new CompositeFrame(baseFrame=frame, []) instanceof CompositeFrame);
        });
        it("overlayFrames consistency", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([1, 1], [5, 5], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            assert.exists(new CompositeFrame(baseFrame, overlayFrames));
            overlayFrames = [
                {frame: new Frame([51, 51], [55, 55], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            assert.exists(new CompositeFrame(baseFrame, overlayFrames));
            overlayFrames.push({frame: new Frame([1, 1], [11, 5], name="badframe"), origin: new Point([1, 1])});
            try {
                new CompositeFrame(baseFrame, overlayFrames);
            } catch (e) {
                assert.equal(e, "frame named 'badframe' will not project/fit into baseFrame at specified origin");
            }
            overlayFrames.pop(2);
            overlayFrames.push({frame: new Frame([1, 1], [5, 5], name="badframe"), origin: new Point([9, 1])});
            try {
                new CompositeFrame(baseFrame, overlayFrames);
            } catch (e) {
                assert.equal(e, "frame named 'badframe' will not project/fit into baseFrame at specified origin");
            }
        });
        it("Translation", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([1, 1], [5, 5], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let p = new Point([10, 10]);
            composition.translate(p);
            assert.isTrue(composition.baseFrame.equals(new Frame(baseFrame.origin, baseFrame.corner)));
            composition.overlayFrames.forEach((frame, index) => {
                let test_frame = new Frame(overlayFrames[index]["frame"].origin, overlayFrames[index]["frame"].corner);
                test_frame.translate(p);
                assert.isTrue(frame["frame"].equals(test_frame));
            });
        });
        it("Translation (by name)", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([1, 1], [5, 5], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let p = new Point([10, 10]);
            composition.translate(p, "frame0");
            assert.isTrue(composition.baseFrame.equals(baseFrame));
            overlayFrames[0]["frame"].translate(p);
            let frame = composition.getOverlayFrame("frame0");
            assert.isTrue(frame["frame"].equals(overlayFrames[0]["frame"]));
            frame = composition.getOverlayFrame("frame1");
            assert.isTrue(frame["frame"].equals(overlayFrames[1]["frame"]));
        });
        it("Translation (by name) error", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([1, 1], [5, 5], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let p = new Point([10, 10]);
            assert.equal(composition.translate(p, "noname"), undefined);
        });
        it("Translation (with baseFrame)", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([1, 1], [5, 5], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let p = new Point([10, 10]);
            composition.translate(p, null, true);
            baseFrame.translate(p);
            composition.overlayFrames.map((frame, index) => {
                overlayFrames[index]["frame"].translate(p);
                assert.isTrue(frame["frame"].equals(overlayFrames[index]["frame"]));
            });
        });
        it("Get Overlay Frame by Name", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([1, 1], [5, 5], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let frame = composition.getOverlayFrame("frame0");
            assert.isTrue(frame["frame"].equals(overlayFrames[0]["frame"]));
            frame = composition.getOverlayFrame("noname");
            assert.equal(frame, null);
        });
        it("Equals", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([1, 1], [5, 5], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let anotherComposition = new CompositeFrame(baseFrame, overlayFrames);
            assert.isTrue(composition.equals(anotherComposition));
        });
        it("(not) Equals", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([1, 1], [5, 5], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            let anotherOverlayFrames = [
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])}
            ];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let anotherComposition = new CompositeFrame(baseFrame, anotherOverlayFrames);
            assert.isFalse(composition.equals(anotherComposition));
            anotherOverlayFrames = [
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([0, 0])},
                {frame: new Frame([0, 0], [4, 4], "frame2"), origin: new Point([0, 0])}
            ];
            anotherComposition = new CompositeFrame(baseFrame, anotherOverlayFrames);
            assert.isFalse(composition.equals(anotherComposition));
            let anotherBaseFrame = new DataFrame([0, 0], [11, 13]);
            anotherComposition = new CompositeFrame(anotherBaseFrame, overlayFrames);
            assert.isFalse(composition.equals(anotherComposition));
        });
        it("Project", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([51, 51], [55, 55], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([3, 4])}
            ];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let projections = composition.project();
            let testProjections = {
                "frame0": new Frame([1, 1], [5, 5]),
                "frame1": new Frame([3, 4], [4, 5]),
            };
            assert.isTrue(projections["frame0"].equals(testProjections["frame0"]));
            assert.isTrue(projections["frame1"].equals(testProjections["frame1"]));
        });
        it("Project (by name)", () => {
            let baseFrame = new DataFrame([0, 0], [10, 10]);
            let overlayFrames = [
                {frame: new Frame([51, 51], [55, 55], "frame0"), origin: new Point([1, 1])},
                {frame: new Frame([0, 0], [1, 1], "frame1"), origin: new Point([3, 4])}
            ];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let projectionFrame = composition.project("frame0");
            let testProjections = {
                "frame0": new Frame([1, 1], [5, 5]),
            };
            assert.isTrue(projectionFrame.equals(testProjections["frame0"]));
        });
        it("Intersect and Project 1", () => {
            let baseFrame = new DataFrame([0, 0], [20, 20]);
            let overlayFrames = [];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let frame1 = new Frame([0, 0], [10, 10]);
            let origin1 = new Point([0, 0]);
            let frame2 = new Frame([0, 0], [5, 5]);
            let resultFrame = composition.intersectAndProject(frame1, origin1, frame2);
            let testFrame = new Frame([0, 0], [5, 5]);
            assert.isTrue(resultFrame.equals(testFrame));
        });
        it("Intersect and Project 2", () => {
            let baseFrame = new DataFrame([0, 0], [20, 20]);
            let overlayFrames = [];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let frame1 = new Frame([0, 0], [10, 10]);
            let origin1 = new Point([1, 1]);
            let frame2 = new Frame([0, 0], [5, 5]);
            let resultFrame = composition.intersectAndProject(frame1, origin1, frame2);
            let testFrame = new Frame([1, 1], [6, 6]);
            assert.isTrue(resultFrame.equals(testFrame));
        });
        it("Intersect and Project 3", () => {
            let baseFrame = new DataFrame([0, 0], [20, 20]);
            let overlayFrames = [];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let frame1 = new Frame([100, 100], [110, 110]);
            let origin1 = new Point([1, 1]);
            let frame2 = new Frame([101, 101], [105, 105]);
            let resultFrame = composition.intersectAndProject(frame1, origin1, frame2);
            let testFrame = new Frame([2, 2], [6, 6]);
            assert.isTrue(resultFrame.equals(testFrame));
        });
        it("Intersect and Project (point) 1", () => {
            let baseFrame = new DataFrame([0, 0], [20, 20]);
            let overlayFrames = [];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let frame1 = new Frame([0, 0], [10, 10]);
            let origin1 = new Point([0, 0]);
            let point = new Point([1, 1]);
            let resultPoint = composition.intersectAndProject(frame1, origin1, point);
            let testPoint = new Point([1, 1]);
            assert.isTrue(resultPoint.equals(testPoint));
        });
        it("Intersect and Project (point) 2", () => {
            let baseFrame = new DataFrame([0, 0], [20, 20]);
            let overlayFrames = [];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let frame1 = new Frame([100, 100], [110, 110]);
            let origin1 = new Point([1, 1]);
            let point = new Point([105, 110]);
            let resultPoint = composition.intersectAndProject(frame1, origin1, point);
            let testPoint = new Point([6, 11]);
            assert.isTrue(resultPoint.equals(testPoint));
        });
        it("Intersect and Project (point) 3", () => {
            let baseFrame = new DataFrame([0, 0], [20, 20]);
            let overlayFrames = [];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let frame1 = new Frame([101, 102], [110, 110]);
            let origin1 = new Point([1, 1]);
            let point = new Point([105, 110]);
            let resultPoint = composition.intersectAndProject(frame1, origin1, point);
            let testPoint = new Point([5, 9]);
            assert.isTrue(resultPoint.equals(testPoint));
        });
        it("Intersect and Project (bad origin)", () => {
            let baseFrame = new DataFrame([0, 0], [20, 20]);
            let overlayFrames = [];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let frame1 = new Frame([0, 0], [10, 10]);
            let origin1 = new Point([50, 50]);
            let frame2 = new Frame([0, 0], [5, 5]);
            try {
                let resultFrame = composition.intersectAndProject(frame1, origin1, frame2);
            } catch(e) {
                assert.equal(e, "origin not contained in baseFrame");
            }
        });
        it("Intersect and Project (empty intersection)", () => {
            let baseFrame = new DataFrame([0, 0], [20, 20]);
            let overlayFrames = [];
            let composition = new CompositeFrame(baseFrame, overlayFrames);
            let frame1 = new Frame([0, 0], [10, 10]);
            let origin1 = new Point([0, 0]);
            let frame2 = new Frame([100, 1000], [500, 5000]);
            let resultFrame = composition.intersectAndProject(frame1, origin1, frame2);
            let testFrame = new Frame();
            assert.isTrue(resultFrame.equals(testFrame));
        });
    });
    describe("DataFrame class tests.", () => {
        before(() => {
        });
        after(() => {
        });
        it("Load data (origin [0, 0])", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [
                [0, 0], [0, 1], [1, 1]
            ];
            let origin = new Point([0, 0]);
            frame.load(data, origin);
            for (let y = 0; y < data.length; y++){
                let x_slice = data[y];
                for (let x = 0; x < x_slice.length; x++){
                    let coord = [x + origin.x, y + origin.y];
                    assert.equal(frame.store[coord.toString()], x_slice[x]);
                }
            }
        });
        it("Load data (origin [0, 0] as array)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [
                [0, 0], [0, 1], [1, 1]
            ];
            let origin = [0, 0];
            frame.load(data, origin);
            for (let y = 0; y < data.length; y++){
                let x_slice = data[y];
                for (let x = 0; x < x_slice.length; x++){
                    let coord = [x + origin[0], y + origin[1]];
                    assert.equal(frame.store[coord.toString()], x_slice[x]);
                }
            }
        });
        it("Load data (origin random)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [
                [0, 0], [0, 1], [1, 1]
            ];
            let origin = new Point([5, 5]);
            frame.load(data, origin);
            for (let y = 0; y < data.length; y++){
                let x_slice = data[y];
                for (let x = 0; x < x_slice.length; x++){
                    let coord = [x + origin.x, y + origin.y];
                    assert.equal(frame.store[coord.toString()], x_slice[x]);
                }
            }
        });
        it("Load data (bad origin)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [];
            let origin = new Point([11, 11]);
            try {
                frame.load(data, origin);
            } catch(e){
                assert.equal(e, "Origin is outside of frame.");
            }
        });
        it("Load data (bad y-dim origin)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [
                [0, 0], [0, 1], [1, 1]
            ];
            let origin = new Point([9, 9]);
            try {
                frame.load(data, origin);
            } catch(e){
                assert.equal(e, "Data + origin surpass frame y-dimension.");
            }
        });
        it("Load data (bad y-dim data)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [
                [0, 0], [0, 1], [1, 1],
                [0, 0], [0, 1], [1, 1],
                [0, 0], [0, 1], [1, 1],
                [0, 0], [0, 1], [1, 1],
                [0, 0], [0, 1], [1, 1],
            ];
            let origin = new Point([0, 0]);
            try {
                frame.load(data, origin);
            } catch(e){
                assert.equal(e, "Data + origin surpass frame y-dimension.");
            }
        });
        it("Load data (bad x-dim data)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [
                [0, 0], [0, 1], [1, 1, 1],
            ];
            let origin = new Point([9, 8]);
            try {
                frame.load(data, origin);
            } catch(e){
                assert.equal(e, "Data + origin surpass frame x-dimension.");
            }
        });
        it("Get frame.store value (valid coordinate string)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [
                [0, 0], [0, 1], [1, 1]
            ];
            let origin = new Point([5, 5]);
            frame.load(data, origin);
            assert.equal(frame.get([5, 5].toString()), 0);
            assert.equal(frame.get([6, 6].toString()), 1);
            assert.equal(frame.get([9, 9].toString()), undefined);
        });
        it("Get frame.store value (valid coordinate Array)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [
                [0, 0], [0, 1], [1, 1]
            ];
            let origin = new Point([5, 5]);
            frame.load(data, origin);
            assert.equal(frame.get([5, 5]), 0);
            assert.equal(frame.get([6, 6]), 1);
            assert.equal(frame.get([9, 9]), undefined);
        });
        it("Get frame.store value (valid coordinate Point)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            let data = [
                [0, 0], [0, 1], [1, 1]
            ];
            let origin = new Point([5, 5]);
            frame.load(data, origin);
            assert.equal(frame.get(new Point([5, 5])), 0);
            assert.equal(frame.get(new Point([6, 6])), 1);
            assert.equal(frame.get(new Point([9, 9])), undefined);
        });
        it("Get frame.store value (invalid coordinate)", () => {
            let frame = new DataFrame([0, 0], [10, 10]);
            try {
                frame.get([20, 20].toString());
            } catch(e) {
                assert.equal(e, "Coordinate not in frame.");
            }
            try {
                frame.get([20, 20]);
            } catch(e) {
                assert.equal(e, "Coordinate not in frame.");
            }
            try {
                frame.get(new Point([20, 20]));
            } catch(e) {
                assert.equal(e, "Coordinate not in frame.");
            }
        });
    });
    describe("SelectionFrame class tests.", () => {
        before(() => {
        });
        after(() => {
        });
        it("Translation (cursor at origin)", () => {
            let frame = new SelectionFrame([0, 0], [10, 10], "selection");
            frame.translate([5, 5]);
            assert.isTrue(frame.equals(new SelectionFrame([5, 5], [15, 15])));
            assert.isTrue(frame.cursor.equals(new Point([5, 5])));
        });
        it("Translation (cursor off origin)", () => {
            let frame = new SelectionFrame([0, 0], [10, 10], "selection");
            frame.cursor = new Point([1, 1]);
            frame.translate([5, 5]);
            assert.isTrue(frame.equals(new SelectionFrame([5, 5], [15, 15])));
            assert.isTrue(frame.cursor.equals(new Point([6, 6])));
        });
        it("From Point to Point (basic)", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            frame.fromPointToPoint([5, 5], [15, 15]);
            assert.isTrue(frame.equals(new SelectionFrame([5, 5], [15, 15])));
            assert.isTrue(frame.cursor.equals(new Point([5, 5])));
        });
        it("From Point to Point (flip)", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            frame.fromPointToPoint([15, 15], [5, 5]);
            assert.isTrue(frame.equals(new SelectionFrame([5, 5], [15, 15])));
            assert.isTrue(frame.cursor.equals(new Point([15, 15])));
        });
        it("From Point to Point (basic without cursor)", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            frame.fromPointToPoint([5, 5], [15, 15], false);
            assert.isTrue(frame.equals(new SelectionFrame([5, 5], [15, 15])));
            assert.isTrue(frame.cursor.equals(new Point([0, 0])));
        });
        it("From Point to Point (flip without cursor)", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            frame.fromPointToPoint([15, 15], [5, 5], false);
            assert.isTrue(frame.equals(new SelectionFrame([5, 5], [15, 15])));
            assert.isTrue(frame.cursor.equals(new Point([0, 0])));
        });
        it("Left Points", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            frame.leftPoints.forEach((p, i) => {
                assert.isTrue(p.equals(new Point([0, i])));
            });
        });
        it("Right Points", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            frame.rightPoints.forEach((p, i) => {
                assert.isTrue(p.equals(new Point([10, i])));
            });
        });
        it("Top Points", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            frame.topPoints.forEach((p, i) => {
                assert.isTrue(p.equals(new Point([i, 0])));
            });
        });
        it("Bottom Points", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            frame.bottomPoints.forEach((p, i) => {
                assert.isTrue(p.equals(new Point([i, 10])));
            });
        });
        it("Is At Bottom", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            let point = new Point([5, 10]);
            assert.isTrue(frame.isAtBottom(point));
            point = new Point([5, 5]);
            assert.isFalse(frame.isAtBottom(point));
        });
        it("Is At Top", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            let point = new Point([5, 0]);
            assert.isTrue(frame.isAtTop(point));
            point = new Point([5, 5]);
            assert.isFalse(frame.isAtTop(point));
        });
        it("Is At Right", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            let point = new Point([10, 5]);
            assert.isTrue(frame.isAtRight(point));
            point = new Point([5, 5]);
            assert.isFalse(frame.isAtRight(point));
        });
        it("Is At Left", () => {
            let frame = new SelectionFrame([0, 0], [10, 10]);
            let point = new Point([0, 5]);
            assert.isTrue(frame.isAtLeft(point));
            point = new Point([5, 5]);
            assert.isFalse(frame.isAtLeft(point));
        });

    });
});

describe.skip("Sheet and Update Data Tests", () => {
    var handler;
    before(() => {
        handler = new CellHandler(registry);
        let rootEl = document.createElement('div');
        rootEl.id = "page_root";
        document.body.append(rootEl);
        let createMessage = makeCreateMessage(simpleRoot);
        handler.receive(createMessage);
    });
    after(() => {
        let rootEl = document.querySelector('[data-cell-id="page_root"]');
        if(rootEl){
            rootEl.remove();
        }
    });
    it("Creates a Sheet Cell", () => {
        let child = Object.assign({}, simpleSheet, {
            parentId: simpleRoot.id,
            nameInParent: 'child'
        });
        let updatedParent = Object.assign({}, simpleRoot, {
            namedChildren: {
                child: child
            }
        });
        assert.notExists(handler.activeCells[child.id]);
        let updateMessage = makeUpdateMessage(updatedParent);
        handler.receive(updateMessage);
        let stored = handler.activeCells[child.id];
        assert.exists(stored);
        let sheet = document.querySelector(`[data-cell-id="${simpleSheet.id}"]`);
        assert.exists(sheet);
        let head = document.getElementById(`sheet-${simpleSheet.id}-head`);
        assert.exists(head);
        let body = document.getElementById(`sheet-${simpleSheet.id}-body`);
        assert.exists(body);
    });
});
