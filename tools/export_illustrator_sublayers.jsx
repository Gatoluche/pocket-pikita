#target illustrator

(function () {
    var CANVAS_WIDTH = 446;
    var CANVAS_HEIGHT = 910;
    var scriptFile = new File($.fileName);
    var repoFolder = scriptFile.parent.parent;
    var sourceFile = new File(repoFolder.fsName + "/Pikita V4.ai");
    var outputFolder = new Folder(repoFolder.fsName + "/assets/rig/sublayers");
    var oldInteractionLevel = app.userInteractionLevel;
    var workingCopy = new File(Folder.temp.fsName + "/pikita-export-" + (new Date().getTime()) + ".ai");
    var doc = null;
    var allLayers = [];
    var exportEntries = [];
    var bounds = [Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY,
                  Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY];

    function ensureFolder(folder) {
        if (folder.exists) return;
        if (!folder.create()) throw new Error("Could not create folder: " + folder.fsName);
    }

    function jsonString(value) {
        return "\"" + String(value).replace(/\\/g, "\\\\").replace(/\"/g, "\\\"")
            .replace(/\r/g, "\\r").replace(/\n/g, "\\n") + "\"";
    }

    function slug(value, fallback) {
        var text = String(value);
        if (text == "><") return "base";
        text = text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
        return text.length ? text : fallback;
    }

    function addLayers(layers, parentPath) {
        for (var i = 0; i < layers.length; i++) {
            var layer = layers[i];
            var path = parentPath.concat([layer.name]);
            var record = { layer: layer, path: path, visible: layer.visible };
            allLayers.push(record);
            addLayers(layer.layers, path);
        }
    }

    function findRecord(layer) {
        for (var i = 0; i < allLayers.length; i++) {
            if (allLayers[i].layer == layer) return allLayers[i];
        }
        return null;
    }

    function layerIsUnder(itemLayer, targetLayer) {
        var current = itemLayer;
        while (current && current.typename == "Layer") {
            if (current == targetLayer) return true;
            current = current.parent;
        }
        return false;
    }

    function itemLayer(item) {
        var current = item;
        while (current && current.typename != "Layer") current = current.parent;
        return current;
    }

    function layerAndParentsWereVisible(layer) {
        var current = layer;
        while (current && current.typename == "Layer") {
            var record = findRecord(current);
            if (!record || !record.visible) return false;
            current = current.parent;
        }
        return true;
    }

    function includeItem(item) {
        try {
            if (item.hidden) return false;
        } catch (e) {}
        var owner = itemLayer(item);
        return owner && layerAndParentsWereVisible(owner);
    }

    function measureContent() {
        for (var i = 0; i < doc.pageItems.length; i++) {
            var item = doc.pageItems[i];
            if (!includeItem(item)) continue;
            var itemBounds;
            try { itemBounds = item.visibleBounds; } catch (e) { continue; }
            if (!itemBounds || itemBounds.length < 4) continue;
            bounds[0] = Math.min(bounds[0], itemBounds[0]);
            bounds[1] = Math.max(bounds[1], itemBounds[1]);
            bounds[2] = Math.max(bounds[2], itemBounds[2]);
            bounds[3] = Math.min(bounds[3], itemBounds[3]);
        }
        if (!isFinite(bounds[0]) || !isFinite(bounds[1]) || !isFinite(bounds[2]) || !isFinite(bounds[3])) {
            throw new Error("No visible artwork was found in the Illustrator document.");
        }
    }

    function visitVisibleLayers(layers, path, callback) {
        for (var i = 0; i < layers.length; i++) {
            var layer = layers[i];
            var record = findRecord(layer);
            if (!record || !record.visible) continue;
            var nextPath = path.concat([layer.name]);
            callback(layer, nextPath);
            visitVisibleLayers(layer.layers, nextPath, callback);
        }
    }

    function isolate(target) {
        for (var i = 0; i < allLayers.length; i++) {
            var record = allLayers[i];
            record.layer.visible = record.visible && layerIsUnder(target, record.layer) ||
                record.visible && layerIsUnder(record.layer, target);
        }
    }

    function outputPathFor(path) {
        var segments = [];
        for (var i = 0; i < path.length; i++) segments.push(slug(path[i], "layer_" + i));
        var name = segments.pop() + ".png";
        var folder = outputFolder;
        for (var j = 0; j < segments.length; j++) {
            folder = new Folder(folder.fsName + "/" + segments[j]);
            ensureFolder(folder);
        }
        return { file: new File(folder.fsName + "/" + name), relative: segments.concat([name]).join("/") };
    }

    function exportLayer(layer, path) {
        isolate(layer);
        var output = outputPathFor(path);
        var options = new ExportOptionsPNG24();
        options.antiAliasing = true;
        options.transparency = true;
        options.artBoardClipping = true;
        options.horizontalScale = (CANVAS_WIDTH / (bounds[2] - bounds[0])) * 100;
        options.verticalScale = (CANVAS_HEIGHT / (bounds[1] - bounds[3])) * 100;
        doc.exportFile(output.file, ExportType.PNG24, options);

        exportEntries.push({
            path: path,
            file: output.relative,
            visible: true
        });
    }

    function writeManifest() {
        var file = new File(outputFolder.fsName + "/manifest.json");
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Could not write manifest: " + file.fsName);
        file.write("{\n  \"source_file\": " + jsonString(sourceFile.name) + ",\n");
        file.write("  \"canvas_size\": [" + CANVAS_WIDTH + ", " + CANVAS_HEIGHT + "],\n");
        file.write("  \"content_bounds_points\": [" + bounds.join(", ") + "],\n");
        file.write("  \"exports\": [\n");
        for (var i = 0; i < exportEntries.length; i++) {
            var entry = exportEntries[i];
            file.write("    {\"path\": [");
            for (var j = 0; j < entry.path.length; j++) {
                if (j) file.write(", ");
                file.write(jsonString(entry.path[j]));
            }
            file.write("], \"file\": " + jsonString(entry.file) + "}");
            file.write(i + 1 == exportEntries.length ? "\n" : ",\n");
        }
        file.write("  ]\n}\n");
        file.close();
    }

    try {
        if (!sourceFile.exists) throw new Error("Source Illustrator file not found: " + sourceFile.fsName);
        ensureFolder(outputFolder);
        if (!sourceFile.copy(workingCopy.fsName)) throw new Error("Could not create a temporary Illustrator copy.");

        app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
        doc = app.open(workingCopy);
        addLayers(doc.layers, []);
        measureContent();

        var artboard = doc.artboards.add(bounds);
        doc.artboards.setActiveArtboardIndex(doc.artboards.length - 1);
        visitVisibleLayers(doc.layers, [], function (layer, path) {
            exportLayer(layer, path);
        });

        writeManifest();
        doc.close(SaveOptions.DONOTSAVECHANGES);
        doc = null;
        workingCopy.remove();
        app.userInteractionLevel = oldInteractionLevel;
        alert("Exported " + exportEntries.length + " visible Illustrator layers and sublayers to:\n" + outputFolder.fsName);
    } catch (error) {
        try { if (doc) doc.close(SaveOptions.DONOTSAVECHANGES); } catch (closeError) {}
        try { if (workingCopy.exists) workingCopy.remove(); } catch (removeError) {}
        app.userInteractionLevel = oldInteractionLevel;
        alert("Illustrator layer export failed:\n" + error.message + (error.line ? "\nLine: " + error.line : ""));
    }
}());
