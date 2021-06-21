# TODO: This is a mix of MIT licensed code (annotated with "MIT
# license") from objgraph and ASL2 license (everything else).  If we
# ever merge something like this, we need to properly document that.

import objgraph
import logging
import time
import threading
import os
import psutil


class BackgroundSearch:
    def __init__(self, scheduler, target):
        log = logging.getLogger('zuul.leak')
        self.search_sleep = 10
        self.scheduler = scheduler
        self.target = target
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

    # MIT license
    def _find_chain(self, obj, predicate, edge_func, max_depth=20, extra_ignore=()):
        queue = [obj]
        depth = {id(obj): 0}
        parent = {id(obj): None}
        ignore = set(extra_ignore)
        ignore.add(id(extra_ignore))
        ignore.add(id(queue))
        ignore.add(id(depth))
        ignore.add(id(parent))
        ignore.add(id(ignore))
        ignore.add(id(sys._getframe()))   # this function
        ignore.add(id(sys._getframe(1)))  # find_chain/find_backref_chain
        gc.collect()
        while queue and self.searching:
            target = queue.pop(0)
            if predicate(target):
                chain = [target]
                while parent[id(target)] is not None:
                    target = parent[id(target)]
                    chain.append(target)
                return chain
            tdepth = depth[id(target)]
            if tdepth < max_depth:
                if not self.searching:
                    return None
                referrers = edge_func(target)
                ignore.add(id(referrers))
                for source in referrers:
                    if id(source) in ignore:
                        continue
                    if id(source) not in depth:
                        depth[id(source)] = tdepth + 1
                        parent[id(source)] = target
                        queue.append(source)
        return [obj]  # not found

    # MIT license
    def find_backref_chain(obj, predicate, max_depth=20, extra_ignore=()):
        return self._find_chain(obj, predicate, gc.get_referrers,
                                max_depth=max_depth, extra_ignore=extra_ignore)

    # MIT license
    def find_ref_chain(obj, predicate, max_depth=20, extra_ignore=()):
        return self._find_chain(obj, predicate, gc.get_referents,
                                max_depth=max_depth, extra_ignore=extra_ignore)

    def run(self):
        while self.target:
            # Assumes target is a layout
            uuid = self.target.uuid
            chain = self.find_ref_chain(self.scheduler,
                                        lambda: x: x is self.target,
                                        max_depth=50,
                                        extra_ignore=[id(self)])
            if not self.target:
                continue
            self.log.warning("Found chain of length %s for %s", len(chain), uuid)
            objgraph.show_chain(chain, filename=f'/var/log/zuul/{uuid}.dot')
        self.target = None

    def stop(self):
        self.target = None


class LeakJanitor:
    def __init__(self, scheduler):
        log = logging.getLogger('zuul.leak')
        self.memory_limit = 28 * 1073741824
        self.search = None
        self.stopped = False
        self.scheduler = scheduler
        self.leak_thread = threading.Thread(target=self.run)
        self.leak_thread.daemon = True
        self.leak_thread.start()

    def run(self):
        self.log.info('Starting leak thread')
        while not self.stopped:
            if self.search and not self.search.target:
                self.search = None
            process = psutil.Process(os.getpid())
            if process.memory_info().rss < self.memory_limit:
                self.runSearch()
            else:
                if self.search:
                    self.search.stop()
                    self.search = None
                self.runCleanup()
            time.sleep(600)
        self.log.info('Stopped')

    def runSearch(self):
        self.log.info('Locking run_handler for search')
        with self.scheduler.run_handler_lock:
            self.log.info('Locked run_handler')
            all_layouts = set(objgraph.by_type('Layout'))
            known_layouts = set()
            for tenant in self.scheduler.abide.tenants.values():
                known_layouts.add(tenant.layout)
                for pipeline in tenant.layout.pipelines.values():
                    for layout in pipeline.manager._layout_cache.values():
                        known_layouts.add(layout)
            leaked_layouts = list(all_layouts - known_layouts)
        del all_layouts
        del known_layouts
        for layout in leaked_layouts:
            if not hasattr(layout, 'tenant'):
                continue
            if not self.search:
                self.log.warning('Found leaked layout %s, '
                                 'searching for backrefs', layout.uuid)
                self.search = BackgroundSearch(self.scheduler, layout)
                continue
            if layout is self.search.target:
                continue
            self.log.warning('Clearing leaked layout %s', layout.uuid)
            layout.__dict__.clear()
        self.log.warning('Total leaked layouts: %s', len(leaked_layouts))
        del leaked_layouts
        self.log.info('Done')

    def runCleanup(self):
        self.log.info('Locking run_handler for cleanup')
        with s.run_handler_lock:
            self.log.info('Locked run_handler')
            all_layouts = set(objgraph.by_type('Layout'))
            known_layouts = set()
            for tenant in s.abide.tenants.values():
                known_layouts.add(tenant.layout)
                for pipeline in tenant.layout.pipelines.values():
                    for layout in pipeline.manager._layout_cache.values():
                        known_layouts.add(layout)
            leaked_layouts = list(all_layouts - known_layouts)
            all_pipelines = set(objgraph.by_type('Pipeline'))
            known_pipelines = set()
            for tenant in s.abide.tenants.values():
                for pipeline in tenant.layout.pipelines.values():
                    known_pipelines.add(pipeline)
            leaked_pipelines = list(all_pipelines - known_pipelines)
            del all_pipelines
            del known_pipelines
        del all_layouts
        del known_layouts
        for layout in leaked_layouts:
            if not hasattr(layout, 'tenant'):
                continue
            self.log.warning('Cleaning leaked layout %s', layout.uuid)
            layout.__dict__.clear()
        for pipeline in leaked_pipelines:
            if not hasattr(pipeline, 'name'):
                continue
            self.log.warning('Cleaning leaked pipeline %s', pipeline)
            pipeline.__dict__.clear()
        self.log.warning('Total leaked layouts: %s', len(leaked_layouts))
        self.log.warning('Total leaked pipelines: %s', len(leaked_pipelines))
        del leaked_layouts
        del leaked_pipelines
        self.log.info('Done')
