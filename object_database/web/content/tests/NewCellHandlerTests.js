/**
 * Tests for Message Handling in NewCellHandler
 */
require('jsdom-global')();
const maquette = require('maquette');
const h = maquette.h;
const NewCellHandler = require('../NewCellHandler.js').default;
const chai = require('chai');
const assert = chai.assert;
let projector = maquette.createProjector();
const registry = require('../ComponentRegistry').ComponentRegistry;

/* Example Messages and Structures */
let simpleRoot = {
    id: "page_root",
    cellType: "RootCell",
    parentId: null,
    nameInParent: null,
    extraData: {},
    namedChildren: {}
};

let firstText = {
    id: 3,
    cellType: "Text",
    extraData: {
        rawText: "Hello"
    },
    namedChildren: {}
};

let secondText = {
    id: 3,
    cellType: "Text",
    extraData: {
        rawText: "Hello"
    },
    namedChildren: {}
};

let simpleSequence = {
    id: 2,
    cellType: "Sequence",
    extraData: {},
    namedChildren: {
        "elements": []
    }
};

let simpleNestedStructure = Object.assign({}, simpleRoot, {
    namedChildren: {
        "child": Object.assign({}, simpleSequence, {
            id: 2,
            nameInParent: "child",
            parentId: 1,
            namedChildren: {
                "elements": [
                    Object.assign({}, firstText, {
                        id: 3,
                        nameInParent: "elements",
                        parentId: 2
                    }),
                    Object.assign({}, secondText, {
                        id: 4,
                        nameInParent: "elements",
                        parentId: 2
                    })
                ]
            }
        })
    }
});
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

describe("Basic NewCellHandler Tests", () => {
    it('Should be able to initialize', () => {
        let instance = new NewCellHandler(h, projector, registry);
        assert.exists(instance);
    });
    it('Has the passed in projector', () => {
        let handler = new NewCellHandler(h, projector, registry);
        assert.equal(projector, handler.projector);
    });
    it('Has the passed in hyperscript constructor', () => {
        let handler = new NewCellHandler(h, projector, registry);
        assert.equal(h, handler.h);
    });
});

describe("Basic Test DOM Tests", () => {
    it("Has a document and body", () => {
        assert.exists(document.body);
    });
    it("Can create and append root element", () => {
        let root = document.createElement('div');
        root.id = "page_root";
        document.body.append(root);
        let found = document.getElementById('page_root');
        assert.exists(found);
        assert.equal(found, root);
    });

    after(() => {
        let root = document.getElementById('page_root');
        if(root){
            root.remove();
        }
    });
});

describe("Basic Structure Handling Component Tests", () => {
    var handler = new NewCellHandler(h, projector, registry);
    before(() => {
        let rootEl = document.createElement('div');
        rootEl.id = 'page_root';
        document.body.append(rootEl);
    });
    after(() => {
        let rootEl = document.getElementById('page_root');
        rootEl.remove();
    });

    it("Creates and stores new RootCell instance", () => {
        let createMessage = makeCreateMessage(simpleRoot);
        handler.receive(createMessage);
        let stored = handler.activeComponents[simpleRoot.id];
        assert.exists(stored);
    });
    it("Initial RootCell instance has no named children", () => {
        let rootComponent = handler.activeComponents[simpleRoot.id];
        assert.notExists(rootComponent.props.namedChildren['child']);
    });
    it("Creates and stores a new TextCell component", () => {
        let child = Object.assign({}, firstText, {
            parentId: simpleRoot.id,
            nameInParent: 'child'
        });
        let updatedParent = Object.assign({}, simpleRoot, {
            namedChildren: {
                child: child
            }
        });
        assert.notExists(handler.activeComponents[child.id]);
        let updateMessage = makeUpdateMessage(updatedParent);
        handler.receive(updateMessage);
        let stored = handler.activeComponents[child.id];
        assert.exists(stored);
    });
    it("RootCell has namedChild 'child' that matches Text component", () => {
        let textComp = handler.activeComponents[firstText.id];
        let parent = handler.activeComponents[simpleRoot.id];
        let namedChild = parent.props.namedChildren['child'];
        assert.equal(textComp, namedChild);
    });
    it("Text component parent attribute set to Root", () => {
        let textComp = handler.activeComponents[firstText.id];
        let parent = handler.activeComponents[simpleRoot.id];
        assert.equal(textComp.parent, parent);
    });
    it("Text component is present in the handler's store", () => {
        let found = handler.activeComponents[firstText.id];
        assert.exists(found);
        assert.equal(found.name, "Text");
    });
    it("Text component has rawText prop value 'WORLD' after update", () => {
        let textComp = handler.activeComponents[firstText.id];
        let updatedText = Object.assign({}, firstText, {
            extraData: {
                rawText: "WORLD"
            }
        });
        let updateMessage = makeUpdateMessage(updatedText);
        let foo = handler.receive(updateMessage);
        assert.equal(handler.activeComponents[firstText.id], foo);
        assert.equal(textComp.props.rawText, "WORLD");
    });
});

describe("Basic Structure Handling DOM Tests", () => {
    var handler;
    before(() => {
        let root = document.createElement('div');
        root.id = "page_root";
        document.body.append(root);
    });

    after(() => {
        let root = document.getElementById('page_root');
        if(root){
            root.remove();
        }
    });

    it("Properly renders new Root Component to the DOM", () => {
        handler = new NewCellHandler(h, projector, registry);
        let createMessage = makeCreateMessage(simpleRoot);
        handler.receive(createMessage);
        let pageRoot = document.getElementById('page_root');
        let inlineType = pageRoot.dataset.cellType;
        assert.exists(inlineType);
        assert.equal(inlineType, "RootCell");
    });
    describe("Can render text cell child on subsequent update", () => {
        before(() => {
            handler = new NewCellHandler(h, projector, registry);
        });
        it("Can receive update message without error", () => {
            let newText = Object.assign({}, firstText, {
                id: 7,
                parentId: simpleRoot.id,
                nameInParent: "child"
            });
            let struct = Object.assign({}, simpleRoot, {
                namedChildren: {
                    child: newText
                }
            });
            let updateMessage = makeUpdateMessage(struct);
            handler.receive(updateMessage);
            assert.equal(Object.keys(handler.activeComponents).length, 2);
        });
        it("Has a RootCell in the DOM", () => {
            assert.equal(Object.keys(handler.activeComponents).length, 2);
            let pageRoot = document.getElementById("page_root");
            assert.exists(pageRoot);
            let cellType = pageRoot.dataset.cellType;
            assert.exists(cellType);
            assert.equal(cellType, "RootCell");
        });
        it("Added a new Component to the handler for Text", () => {
            let found = handler.activeComponents[7];
            assert.exists(found);
        });
        it("Has a Text cell in the DOM under RootCell", () => {
            let pageRoot = document.getElementById("page_root");
            let textChild = pageRoot.querySelector(".cell");
            assert.exists(textChild);
        });
        it("Can replace the existing child", () => {
            let newText = Object.assign({}, firstText, {
                id: 8,
                parentId: 1,
                nameInParent: "child",
                extraData: {
                    rawText: "FARTS"
                }
            });
            let parent = Object.assign({}, simpleRoot, {
                namedChildren: {
                    child: newText
                }
            });
            let updateMessage = makeUpdateMessage(parent);
            handler.receive(updateMessage);
            let pageRoot = document.getElementById(simpleRoot.id);
            assert.equal(pageRoot.children.length, 1);
            let textChild = pageRoot.firstElementChild;
            assert.exists(textChild);
            assert.equal(textChild.textContent, "FARTS");
            assert.equal(textChild.id, 8);
        });
    });
});

describe("Properties Update Tests", () => {
    var handler;
    before(() => {
        handler = new NewCellHandler(h, projector, registry);
        let rootEl = document.createElement('div');
        rootEl.id = "page_root";
        document.body.append(rootEl);
    });
    after(() => {
        let rootEl = document.getElementById('page_root');
        if(rootEl){
            rootEl.remove();
        }
    });
    it("Creates a Text Cell whose content is 'HELLO'", () => {
        let newText = Object.assign({}, firstText, {
            id: 2,
            nameInParent: "child",
            parentId: 1,
            extraData: {
                rawText: "HELLO"
            }
        });
        let parent = Object.assign({}, simpleRoot, {
            namedChildren: {
                child: newText
            }
        });
        let updateMessage = makeUpdateMessage(parent);
        handler.receive(updateMessage);
        let el = document.getElementById(newText.id);
        assert.exists(el);
        assert.equal(el.textContent, "HELLO");
    });
    it("Has text 'WORLD' after props update", function(){
        let newText = Object.assign({}, firstText, {
            id: 2,
            parentId: simpleRoot.id,
            nameInParent: "child",
            extraData: {
                rawText: "WORLD"
            }
        });
        let updateMessage = Object.assign({}, newText, {
            type: "#cellUpdated",
            shouldDisplay: true,
            channel: "#main"
        });
        handler.receive(updateMessage);
        let root = document.getElementById('page_root');
        assert.equal(root.children.length, 1);
        let textChild = document.getElementById(newText.id);
        assert.equal(textChild.textContent, "WORLD");
    });
});
