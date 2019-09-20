from enzi.file_manager import LocalFiles, FileManager

class ProjectFiles(FileManager):
    def __init__(self, enzi_project):
        self.lf_managers = {}
        self.cache_files = {}
        for target in enzi_project.targets:
            # print('found target:', target)
            fileset = enzi_project.gen_target_fileset(target)
            config = {'fileset': fileset}
            self.lf_managers[target] = LocalFiles(
                config, enzi_project.work_dir, enzi_project.build_dir)
            self.cache_files[target] = { 'files': [] }

        self.default_target = next(iter(enzi_project.targets.keys()))
        super(ProjectFiles, self).__init__({}, enzi_project.work_dir, enzi_project.build_dir)

    def fetch(self, target_name=None):
        if not target_name:
            target_name = self.default_target
        elif not target_name in self.lf_managers.keys():
            raise RuntimeError('Unknown target {}.'.format(target_name))

        ccfiles = self.lf_managers[target_name].fetch()
        self.cache_files[target_name] = ccfiles
    
    def clean_cache(self):
        for _, lf_manager in self.lf_managers.items():
            lf_manager.clean_cache()

    def get_fileset(self, target_name=None):
        if not target_name:
            target_name = self.default_target
        elif not target_name in self.lf_managers.keys():
            raise RuntimeError('target {} is not fetched.'.format(target_name))

        return self.lf_managers[target_name].fileset
