from stgan_adain.model import Generator
from stgan_adain.model import PatchDiscriminator 
from stgan_adain.model import Discriminator
from stgan_adain.model import SPEncoder
from stgan_adain.model import SPEncoderPool 
from stgan_adain.model import SPEncoderPool1D
import torch
import torch.nn.functional as F
from os.path import join, basename
import time
import datetime
from data_loader import to_categorical
from utils import *
from tqdm import tqdm
import numpy as np

class Solver(object):
    """Solver for training and testing StarGAN."""

    def __init__(self, train_loader, test_loader, config):
        """Initialize configurations."""

        # Data loader.
        self.train_loader = train_loader
        self.test_loader = test_loader
        self.sampling_rate = config.sampling_rate

        # submodules
        self.D_name = config.discriminator
        self.SPE_name = config.spenc

        # Model configurations.
        self.num_speakers = config.num_speakers
        self.lambda_rec = config.lambda_rec
        self.lambda_gp = config.lambda_gp
        self.lambda_id = config.lambda_id
        self.lambda_spid = config.lambda_spid
        self.lambda_adv = config.lambda_adv    
        self.lambda_cls = config.lambda_cls
        self.drop_id_step = config.drop_id_step
        self.spk_cls = config.spk_cls

        # Training configurations.
        self.batch_size = config.batch_size
        self.num_iters = config.num_iters
        self.num_iters_decay = config.num_iters_decay
        self.g_lr = config.g_lr
        self.d_lr = config.d_lr
        self.n_critic = config.n_critic
        self.beta1 = config.beta1
        self.beta2 = config.beta2
        self.resume_iters = config.resume_iters

        # Test configurations.
        self.test_iters = config.test_iters

        # Miscellaneous.
        self.use_tensorboard = config.use_tensorboard
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Directories.
        self.log_dir = config.log_dir
        self.sample_dir = config.sample_dir
        self.model_save_dir = config.model_save_dir

        # Step size.
        self.log_step = config.log_step
        self.sample_step = config.sample_step
        self.model_save_step = config.model_save_step
        self.lr_update_step = config.lr_update_step

        # Build the model and tensorboard.
        self.build_model()
        if self.use_tensorboard:
            self.build_tensorboard()

    def build_model(self):
        """Create a generator and a discriminator."""
        self.generator = Generator(num_speakers=self.num_speakers)
        self.discriminator = eval(self.D_name)(num_speakers=self.num_speakers)
        self.sp_enc = eval(self.SPE_name)(num_speakers = self.num_speakers, spk_cls = self.spk_cls)

        self.g_optimizer = torch.optim.Adam(list(self.generator.parameters()) + list(self.sp_enc.parameters()), self.g_lr, [self.beta1, self.beta2])
        self.d_optimizer = torch.optim.Adam(self.discriminator.parameters(), self.d_lr, [self.beta1, self.beta2])

        self.print_network(self.generator, 'Generator')
        self.print_network(self.discriminator, 'Discriminator')
        self.print_network(self.sp_enc, 'SpeakerEncoder')

        self.generator.to(self.device)
        self.discriminator.to(self.device)
        self.sp_enc.to(self.device)

    def print_network(self, model, name):
        """Print out the network information."""
        num_params = 0
        for p in model.parameters():
            num_params += p.numel()
        print(model, flush=True)
        print(name,flush=True)
        print("The number of parameters: {}".format(num_params), flush=True)

    def restore_model(self, resume_iters):
        """Restore the trained generator and discriminator."""
        print('Loading the trained models from step {}...'.format(resume_iters), flush=True)
        g_path = os.path.join(self.model_save_dir, '{}-G.ckpt'.format(resume_iters))
        d_path = os.path.join(self.model_save_dir, '{}-D.ckpt'.format(resume_iters))
        sp_path = os.path.join(self.model_save_dir, '{}-sp.ckpt'.format(resume_iters))

        self.generator.load_state_dict(torch.load(g_path, map_location=lambda storage, loc: storage))
        self.discriminator.load_state_dict(torch.load(d_path, map_location=lambda storage, loc: storage))
        self.sp_enc.load_state_dict(torch.load(sp_path, map_location=lambda storage, loc: storage))

    def build_tensorboard(self):
        """Build a tensorboard logger."""
        from logger import Logger
        self.logger = Logger(self.log_dir)

    def update_lr(self, g_lr, d_lr):
        """Decay learning rates of the generator and discriminator."""
        for param_group in self.g_optimizer.param_groups:
            param_group['lr'] = g_lr
        for param_group in self.d_optimizer.param_groups:
            param_group['lr'] = d_lr

    def reset_grad(self):
        """Reset the gradientgradient buffers."""
        self.g_optimizer.zero_grad()
        self.d_optimizer.zero_grad()

    def denorm(self, x):
        """Convert the range from [-1, 1] to [0, 1]."""
        out = (x + 1) / 2
        return out.clamp_(0, 1)

    def gradient_penalty(self, y, x):
        """Compute gradient penalty: (L2_norm(dy/dx) - 1)**2."""
        weight = torch.ones(y.size()).to(self.device)
        dydx = torch.autograd.grad(outputs=y,
                                   inputs=x,
                                   grad_outputs=weight,
                                   retain_graph=True,
                                   create_graph=True,
                                   only_inputs=True)[0]

        dydx = dydx.view(dydx.size(0), -1)
        dydx_l2norm = torch.sqrt(torch.sum(dydx**2, dim=1))
        return torch.mean((dydx_l2norm-1)**2)

    def label2onehot(self, labels, dim):
        """Convert label indices to one-hot vectors."""
        batch_size = labels.size(0)
        out = torch.zeros(batch_size, dim)
        out[np.arange(batch_size), labels.long()] = 1
        return out

    def sample_spk_c(self, size):
        spk_c = np.random.randint(0, self.num_speakers, size=size)
        spk_c_cat = to_categorical(spk_c, self.num_speakers)
        return torch.LongTensor(spk_c), torch.FloatTensor(spk_c_cat)

    def classification_loss(self, logit, target):
        """Compute softmax cross entropy loss."""
        return F.cross_entropy(logit, target)

    def load_wav(self, wavfile, sr=16000):
        wav, _ = librosa.load(wavfile, sr=sr, mono=True)
        return wav_padding(wav, sr=16000, frame_period=5, multiple = 4)

    def train(self):
        """Train StarGAN."""
        # Set data loader.
        train_loader = self.train_loader
        data_iter = iter(train_loader)

        # Read a batch of testdata
        test_wavfiles = self.test_loader.get_batch_test_data(batch_size=10)
        test_wavs = [(self.load_wav(wavfile, sr = self.sampling_rate), mc_src, mc_trg) for (wavfile, mc_src, mc_trg) in test_wavfiles]

        # Determine whether do copysynthesize when first do training-time conversion test.
        cpsyn_flag = [True, False][0]
        # f0, timeaxis, sp, ap = world_decompose(wav = wav, fs = sampling_rate, frame_period = frame_period)

        # Learning rate cache for decaying.
        g_lr = self.g_lr
        d_lr = self.d_lr

        # Start training from scratch or resume training.
        start_iters = 0
        if self.resume_iters:
            print("resuming step %d ..."% self.resume_iters, flush=True)
            start_iters = self.resume_iters
            self.restore_model(self.resume_iters)

        # Start training.
        print('Start training...', flush=True)
        start_time = time.time()
        for i in range(start_iters, self.num_iters):
            # =================================================================================== #
            #                             1. Preprocess input data                                #
            # =================================================================================== #

            # Fetch labels.
            '''
            try:
                mc_real, spk_label_org, spk_c_org = next(data_iter)
            except:
                data_iter = iter(train_loader)
                mc_real, spk_label_org, spk_c_org = next(data_iter)

            '''

            try:
                mc_src, spk_label_org, spk_c_org, mc_trg, spk_label_trg, spk_c_trg = next(data_iter)
            except:
                data_iter = iter(train_loader)
                mc_src, spk_label_org, spk_c_org, mc_trg, spk_label_trg, spk_c_trg = next(data_iter)
            
            mc_src.unsqueeze_(1) # (B, D, T) -> (B, 1, D, T) for conv2d
            mc_trg.unsqueeze_(1) # (B, D, T) -> (B, 1, D, T) for conv2d

            # Generate target domain labels randomly.
            # spk_label_trg: int,   spk_c_trg:one-hot representation
            #spk_label_trg, spk_c_trg = self.sample_spk_c(mc_real.size(0))

            mc_src = mc_src.to(self.device)              # Input mc.
            mc_trg = mc_trg.to(self.device)              # Input mc.
            spk_label_org = spk_label_org.to(self.device)  # Original spk labels.
            spk_c_org = spk_c_org.to(self.device)          # Original spk one-hot.
            spk_label_trg = spk_label_trg.to(self.device)  # Target spk labels.
            spk_c_trg = spk_c_trg.to(self.device)          # Target spk one-hot.

            # =================================================================================== #
            #                             2. Train the Discriminator                              #
            # =================================================================================== #
            pretrain_step = -1
            if i > pretrain_step:
                # org and trg speaker cond
                spk_c_trg = self.sp_enc(mc_trg, spk_label_trg)
                spk_c_org = self.sp_enc(mc_src, spk_label_org)


                # Compute loss with face mc feats.
                mc_fake = self.generator(mc_src, spk_c_org, spk_c_trg)
                d_out_fake = self.discriminator(mc_fake.detach(), spk_label_org, spk_label_trg)
                #d_loss_fake =  torch.mean(d_out_fake)
                d_loss_fake = torch.mean(d_out_fake ** 2)

                # Compute loss with real mc feats.
                d_out_src = self.discriminator(mc_src, spk_label_trg, spk_label_org)
                #d_loss_real = - torch.mean(d_out_src)
                d_loss_real = torch.mean(  (1.0 - d_out_src)**2  )


                # Compute loss for gradient penalty.
                #alpha = torch.rand(mc_src.size(0), 1, 1, 1).to(self.device)
                #alpha = torch.rand(mc_trg.size(0), 1, 1, 1).to(self.device)
                #x_hat = (alpha * mc_trg.data + (1 - alpha) * mc_fake.data).requires_grad_(True)
                #d_out_src = self.discriminator(x_hat, spk_c_org, spk_c_trg)
                #d_loss_gp = self.gradient_penalty(d_out_src, x_hat)
                
                #x_hat = mc_src.requires_grad_()
                #d_out_src = self.discriminator(x_hat, spk_c_trg, spk_c_org)
                #d_loss_gp = self.gradient_penalty(d_out_src, x_hat)

                # Backward and optimize.
                #d_loss = d_loss_real + d_loss_fake + self.lambda_gp * d_loss_gp
                d_loss = self.lambda_adv * (d_loss_real + d_loss_fake)
                self.reset_grad()
                d_loss.backward()
                self.d_optimizer.step()

                # Logging.
                loss = {}
                loss['D/loss_real'] = d_loss_real.item()
                loss['D/loss_fake'] = d_loss_fake.item()
                #loss['D/loss_gp'] = d_loss_gp.item()
                loss['D/loss'] = d_loss.item()

            # =================================================================================== #
            #                               3. Train the generator                                #
            # =================================================================================== #
            if (i+1) % self.n_critic == 0:
                
                # org and trg speaker cond
                
                if self.spk_cls:

                    spk_c_trg, cls_out_trg = self.sp_enc(mc_trg, spk_label_trg, cls_out = True)
                    spk_c_org, cls_out_org = self.sp_enc(mc_src, spk_label_org, cls_out = True)
                    
                    cls_loss = self.classification_loss(cls_out_trg, spk_label_trg) + self.classification_loss(cls_out_org, spk_label_org)   
                else:
                    spk_c_trg = self.sp_enc(mc_trg, spk_label_trg)
                    spk_c_org = self.sp_enc(mc_src, spk_label_org)

                
                # Original-to-target domain.
                mc_fake = self.generator(mc_src, spk_c_org,  spk_c_trg)
                g_out_src = self.discriminator(mc_fake, spk_label_org, spk_label_trg)
                #g_loss_fake = - torch.mean(g_out_src)
                g_loss_fake = torch.mean((1.0 - g_out_src)**2)

                # Target-to-original domain. Cycle-consistent.
                mc_reconst = self.generator(mc_fake, spk_c_trg, spk_c_org)
                g_loss_rec = torch.mean(torch.abs(mc_src - mc_reconst))

                # Original-to-original, Id mapping loss. Mapping
                mc_fake_id = self.generator(mc_src, spk_c_org, spk_c_org)
                g_loss_id = torch.mean(torch.abs(mc_src - mc_fake_id))
                
                # style encoder id loss

                mc_fake_style_c = self.sp_enc(mc_fake, spk_label_trg)
                mc_src_style_c = self.sp_enc(mc_reconst, spk_label_trg)
                g_loss_stid = torch.mean(torch.abs(mc_fake_style_c - spk_c_trg))
                
                #g_loss_stid = torch.log(torch.mean(torch.abs(mc_fake_style_c - spk_c_trg.detach()))) -torch.log( torch.mean(torch.abs(mc_src_style_c - spk_c_org.detach())) )

                if i> self.drop_id_step:
                    self.lambda_id = 0.
                # Backward and optimize.
                g_loss = self.lambda_adv *  g_loss_fake \
                    + self.lambda_rec * g_loss_rec \
                    + self.lambda_id * g_loss_id \
                    + self.lambda_spid * g_loss_stid
                
                if self.spk_cls:
                    g_loss += self.lambda_cls * cls_loss

                self.reset_grad()
                g_loss.backward()
                self.g_optimizer.step()
                # Logging.
                loss['G/loss_fake'] = g_loss_fake.item()
                loss['G/loss_rec'] = g_loss_rec.item()
                #loss['G/loss'] = g_loss.item()
                loss['G/loss_id'] = g_loss_id.item()
                loss['G/loss_stid'] = g_loss_stid.item()
                if self.spk_cls:
                    loss['G/spk_cls'] = cls_loss.item()
            
            # =================================================================================== #
            #                                 4. Miscellaneous                                    #
            # =================================================================================== #

            # Print out training information.
            if (i+1) % self.log_step == 0:
                et = time.time() - start_time
                et = str(datetime.timedelta(seconds=et))[:-7]
                log = "Elapsed [{}], Iteration [{}/{}]".format(et, i+1, self.num_iters)
                for tag, value in loss.items():
                    log += ", {}: {:.4f}".format(tag, value)
                print(log, flush=True)

                if self.use_tensorboard:
                    for tag, value in loss.items():
                        self.logger.scalar_summary(tag, value, i+1)

            # Save model checkpoints.
            if (i+1) % self.model_save_step == 0:
                g_path = os.path.join(self.model_save_dir, '{}-G.ckpt'.format(i+1))
                d_path = os.path.join(self.model_save_dir, '{}-D.ckpt'.format(i+1))
                sp_path = os.path.join(self.model_save_dir, '{}-sp.ckpt'.format(i+1))

                torch.save(self.generator.state_dict(), g_path)
                torch.save(self.discriminator.state_dict(), d_path)
                torch.save(self.sp_enc.state_dict(), sp_path)
                print('Saved model checkpoints into {}...'.format(self.model_save_dir), flush=True)
            
            
            
            
            if i> pretrain_step and (i+1) % self.sample_step == 0:
                sampling_rate = self.sampling_rate
                num_mcep = 36
                frame_period = 5
                with torch.no_grad():
                    for idx, (wav, mc_src, mc_trg) in tqdm(enumerate(test_wavs)):
                        wav_name = basename(test_wavfiles[idx][0])
                        # print(wav_name)
                        f0, timeaxis, sp, ap = world_decompose(wav=wav, fs=sampling_rate, frame_period=frame_period)
                        f0_converted = pitch_conversion(f0=f0,
                            mean_log_src=self.test_loader.logf0s_mean_src, std_log_src=self.test_loader.logf0s_std_src,
                            mean_log_target=self.test_loader.logf0s_mean_trg, std_log_target=self.test_loader.logf0s_std_trg)
                        coded_sp = world_encode_spectral_envelop(sp=sp, fs=sampling_rate, dim=num_mcep)

                        coded_sp_norm = (coded_sp - self.test_loader.mcep_mean_src) / self.test_loader.mcep_std_src
                        coded_sp_norm_tensor = torch.FloatTensor(coded_sp_norm.T).unsqueeze_(0).unsqueeze_(1).to(self.device)
                        
                        
                        trg_idx = torch.LongTensor([self.test_loader.spk_idx]).to(self.device)
                        src_idx = torch.LongTensor([self.test_loader.src_spk_idx]).to(self.device)
                        
                        
                        # print(conds.size())
                        trg_mc = torch.FloatTensor(np.array([mc_trg.T])).unsqueeze_(0).to(self.device)
                        src_mc = torch.FloatTensor(np.array([mc_src.T])).unsqueeze_(0).to(self.device)
                        trg_conds = self.sp_enc(trg_mc, trg_idx )
                        src_conds = self.sp_enc(src_mc, src_idx )
                        coded_sp_converted_norm = self.generator(coded_sp_norm_tensor, src_conds, trg_conds).data.cpu().numpy()
                        coded_sp_converted = np.squeeze(coded_sp_converted_norm).T * self.test_loader.mcep_std_trg + self.test_loader.mcep_mean_trg
                        coded_sp_converted = np.ascontiguousarray(coded_sp_converted)
                        # decoded_sp_converted = world_decode_spectral_envelop(coded_sp = coded_sp_converted, fs = sampling_rate)
                        wav_transformed = world_speech_synthesis(f0=f0_converted, coded_sp=coded_sp_converted,
                                                                ap=ap, fs=sampling_rate, frame_period=frame_period)

                        librosa.output.write_wav(
                            join(self.sample_dir, str(i+1)+'-'+wav_name.split('.')[0]+'-vcto-{}'.format(self.test_loader.trg_spk)+'.wav'), wav_transformed, sampling_rate)
                        if cpsyn_flag:
                            wav_cpsyn = world_speech_synthesis(f0=f0, coded_sp=coded_sp,
                                                        ap=ap, fs=sampling_rate, frame_period=frame_period)
                            librosa.output.write_wav(join(self.sample_dir, 'cpsyn-'+wav_name), wav_cpsyn, sampling_rate)
                    cpsyn_flag = False


            # Decay learning rates.
            #if (i+1) % self.lr_update_step == 0 and (i+1) > (self.num_iters - self.num_iters_decay):
            #    g_lr -= (self.g_lr / float(self.num_iters_decay))
            #    d_lr -= (self.d_lr / float(self.num_iters_decay))
            #    self.update_lr(g_lr, d_lr)
            #    print('Decayed learning rates, g_lr: {}, d_lr: {}'.format(g_lr, d_lr), flush=True)
