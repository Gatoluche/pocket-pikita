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
    var allPageItems = [];
    var visibleGroups = [];
    var exportEntries = [];
    var groupEntries = [];
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

    function addLayers(layers, parentPath, ancestors) {
        for (var i = 0; i < layers.length; i++) {
            var layer = layers[i];
            var path = parentPath.concat([layer.name]);
            var parentRecords = ancestors.slice(0);
            var record = {
                layer: layer,
                path: path,
                visible: layer.visible,
                ancestors: parentRecords
            };
            allLayers.push(record);
            var childAncestors = parentRecords.concat([record]);
            addLayers(layer.layers, path, childAncestors);
        }
    }

    function findRecord(layer) {
        for (var i = 0; i < allLayers.length; i++) {
            if (allLayers[i].layer == layer) return allLayers[i];
        }
        return null;
    }

    function recordIsUnder(record, ancestor) {
        if (record == ancestor) return true;
        for (var i = 0; i < record.ancestors.length; i++) {
            if (record.ancestors[i] == ancestor) return true;
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
        var record = findRecord(current);
        if (!record || !record.visible) return false;
        for (var i = 0; i < record.ancestors.length; i++) {
            if (!record.ancestors[i].visible) return false;
        }
        return true;
    }

    function itemAndParentsWereVisible(item) {
        var current = item;
        while (current && current.typename != "Layer" && current.typename != "Document") {
            var entry = itemRecord(current);
            if (entry && entry.hidden) return false;
            current = current.parent;
        }
        return current && current.typename == "Layer" && layerAndParentsWereVisible(current);
    }

    function includeItem(item) {
        return itemAndParentsWereVisible(item);
    }

    function collectPageItems() {
        for (var i = 0; i < doc.pageItems.length; i++) {
            var item = doc.pageItems[i];
            var hidden = false;
            try { hidden = item.hidden; } catch (e) {}
            allPageItems.push({ item: item, hidden: hidden });
        }
    }

    function itemRecord(item) {
        for (var i = 0; i < allPageItems.length; i++) {
            if (allPageItems[i].item == item) return allPageItems[i];
        }
        return null;
    }

    function isItemUnder(item, target) {
        var current = item;
        while (current && current.typename != "Layer" && current.typename != "Document") {
            if (current == target) return true;
            current = current.parent;
        }
        return false;
    }

    function isRequiredClipMask(candidate, target) {
        var ancestor = target.parent;
        while (ancestor && ancestor.typename != "Layer" && ancestor.typename != "Document") {
            if (ancestor.typename == "GroupItem" && ancestor.clipped && candidate.parent == ancestor) {
                try { if (candidate.clipping) return true; } catch (e) {}
            }
            ancestor = ancestor.parent;
        }
        return false;
    }

    function isVisibleGroup(group) {
        var current = group;
        while (current && current.typename != "Layer" && current.typename != "Document") {
            try { if (current.hidden) return false; } catch (e) {}
            current = current.parent;
        }
        return layerAndParentsWereVisible(itemLayer(group));
    }

    function countVisibleItemsInLayer(targetRecord) {
        var count = 0;
        for (var i = 0; i < allPageItems.length; i++) {
            var entry = allPageItems[i];
            if (entry.hidden || !includeItem(entry.item)) continue;
            var ownerRecord = findRecord(itemLayer(entry.item));
            if (ownerRecord && recordIsUnder(ownerRecord, targetRecord)) count++;
        }
        return count;
    }

    function countItemsInGroup(group) {
        var count = 0;
        for (var i = 0; i < allPageItems.length; i++) {
            var entry = allPageItems[i];
            if (!entry.hidden && isItemUnder(entry.item, group)) count++;
        }
        return count;
    }

    function groupPath(group) {
        var names = [];
        var current = group;
        while (current && current.typename != "Layer" && current.typename != "Document") {
            if (current.typename == "GroupItem") {
                var name = "";
                try { name = current.name; } catch (e) {}
                names.unshift(name || "Group");
            }
            current = current.parent;
        }
        return names;
    }

    function padNumber(value, width) {
        var text = String(value);
        while (text.length < width) text = "0" + text;
        return text;
    }

    function groupOutputPath(layerRecord, group, index) {
        var names = groupPath(group);
        var folder = new Folder(outputFolder.fsName + "/groups");
        ensureFolder(folder);
        for (var i = 0; i < layerRecord.path.length; i++) {
            folder = new Folder(folder.fsName + "/" + slug(layerRecord.path[i], "layer_" + i));
            ensureFolder(folder);
        }
        for (var j = 0; j < names.length - 1; j++) {
            folder = new Folder(folder.fsName + "/" + slug(names[j], "group"));
            ensureFolder(folder);
        }
        var leafName = names.length ? slug(names[names.length - 1], "group") : "group";
        var filename = "group_" + padNumber(index + 1, 4) + "_" + leafName + ".png";
        var relativeParts = ["groups"];
        for (var k = 0; k < layerRecord.path.length; k++) {
            relativeParts.push(slug(layerRecord.path[k], "layer_" + k));
        }
        for (var m = 0; m < names.length - 1; m++) {
            relativeParts.push(slug(names[m], "group"));
        }
        relativeParts.push(filename);
        return {
            file: new File(folder.fsName + "/" + filename),
            relative: relativeParts.join("/")
        };
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

    function isolateLayer(targetRecord) {
        for (var i = 0; i < allLayers.length; i++) {
            var record = allLayers[i];
            var partOfTargetTree = recordIsUnder(record, targetRecord) ||
                recordIsUnder(targetRecord, record);
            record.layer.visible = record.visible && partOfTargetTree;
        }
    }

    function isolateGroup(group) {
        var targetLayer = findRecord(itemLayer(group));
        for (var i = 0; i < allLayers.length; i++) {
            var record = allLayers[i];
            record.layer.visible = record.visible && recordIsUnder(targetLayer, record);
        }

        for (var j = 0; j < allPageItems.length; j++) {
            var entry = allPageItems[j];
            entry.item.hidden = entry.hidden;
        }
        for (var k = 0; k < allPageItems.length; k++) {
            var candidate = allPageItems[k].item;
            var keep = isItemUnder(candidate, group) || isItemUnder(group, candidate) ||
                isRequiredClipMask(candidate, group);
            if (!keep) allPageItems[k].item.hidden = true;
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
        var targetRecord = findRecord(layer);
        isolateLayer(targetRecord);
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
            visible: true,
            page_item_count: countVisibleItemsInLayer(targetRecord)
        });
    }

    function exportGroup(group, index) {
        var ownerRecord = findRecord(itemLayer(group));
        isolateGroup(group);
        var output = groupOutputPath(ownerRecord, group, index);
        var options = new ExportOptionsPNG24();
        options.antiAliasing = true;
        options.transparency = true;
        options.artBoardClipping = true;
        options.horizontalScale = (CANVAS_WIDTH / (bounds[2] - bounds[0])) * 100;
        options.verticalScale = (CANVAS_HEIGHT / (bounds[1] - bounds[3])) * 100;
        doc.exportFile(output.file, ExportType.PNG24, options);

        groupEntries.push({
            layer_path: ownerRecord.path,
            group_path: groupPath(group),
            file: output.relative,
            page_item_count: countItemsInGroup(group)
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
            file.write("], \"file\": " + jsonString(entry.file) +
                ", \"page_item_count\": " + entry.page_item_count + "}");
            file.write(i + 1 == exportEntries.length ? "\n" : ",\n");
        }
        file.write("  ],\n  \"group_exports\": [\n");
        for (var k = 0; k < groupEntries.length; k++) {
            var groupEntry = groupEntries[k];
            file.write("    {\"layer_path\": [");
            for (var m = 0; m < groupEntry.layer_path.length; m++) {
                if (m) file.write(", ");
                file.write(jsonString(groupEntry.layer_path[m]));
            }
            file.write("], \"group_path\": [");
            for (var n = 0; n < groupEntry.group_path.length; n++) {
                if (n) file.write(", ");
                file.write(jsonString(groupEntry.group_path[n]));
            }
            file.write("], \"file\": " + jsonString(groupEntry.file) +
                ", \"page_item_count\": " + groupEntry.page_item_count + "}");
            file.write(k + 1 == groupEntries.length ? "\n" : ",\n");
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
        addLayers(doc.layers, [], []);
        collectPageItems();
        measureContent();

        var artboard = doc.artboards.add(bounds);
        doc.artboards.setActiveArtboardIndex(doc.artboards.length - 1);
        visitVisibleLayers(doc.layers, [], function (layer, path) {
            exportLayer(layer, path);
        });

        for (var groupIndex = 0; groupIndex < doc.groupItems.length; groupIndex++) {
            var group = doc.groupItems[groupIndex];
            if (isVisibleGroup(group)) visibleGroups.push(group);
        }
        for (var exportGroupIndex = 0; exportGroupIndex < visibleGroups.length; exportGroupIndex++) {
            exportGroup(visibleGroups[exportGroupIndex], exportGroupIndex);
        }

        writeManifest();
        doc.close(SaveOptions.DONOTSAVECHANGES);
        doc = null;
        workingCopy.remove();
        app.userInteractionLevel = oldInteractionLevel;
        alert("Exported " + exportEntries.length + " visible Illustrator layers and sublayers, plus " +
            groupEntries.length + " artwork groups, to:\n" + outputFolder.fsName);
    } catch (error) {
        try { if (doc) doc.close(SaveOptions.DONOTSAVECHANGES); } catch (closeError) {}
        try { if (workingCopy.exists) workingCopy.remove(); } catch (removeError) {}
        app.userInteractionLevel = oldInteractionLevel;
        alert("Illustrator layer export failed:\n" + error.message + (error.line ? "\nLine: " + error.line : ""));
    }
}());
